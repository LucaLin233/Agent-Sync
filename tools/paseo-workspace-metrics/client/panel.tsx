import {
  type AgentRef,
  type PluginButtonContentProps,
  type PluginWorkspacePanelProps,
  useSubscription,
  useAgent,
  useAgents,
  useWorkspace,
} from "@getpaseo/plugin/client";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Pressable, ScrollView, Text, View } from "react-native";
import {
  averageFirstTokenMs,
  type CacheSample,
  formatCacheRate,
  formatDurationMs,
  formatTokenCount,
  formatTokenSpeed,
  summarizeLatestSamples,
  tokenCount,
  tokensPerSecond,
  weightedTurnSpeed,
} from "../shared/metrics";
import { scopeQueryKey, workspaceSettingsSubscription, type WorkspaceScope } from "../shared/scope";
import { cumulativeReadEnabled, resolveCumulativeScope, useCumulativeUsage } from "./use-cumulative";
import { useCumulativeHub } from "./cumulative-hub-context";
import {
  publishPanelScope,
  useSharedRevision,
  useSharedScope,
  useSharedScopeStatus,
  useWorkspaceRevision,
} from "./shared-store";
import { useSharedStore } from "./shared-store-context";
import { useLiveTurn } from "./use-turn";
import { useTurnOutput } from "./use-turn-output";
import { useWorkspaceUsage, type UsageSnapshot } from "./use-usage";
import { createSubscriptionRetry } from "./subscription-retry";

type Colors = PluginWorkspacePanelProps["theme"]["colors"];
const dates = new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" });
const monthDayTime = new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false });

/** "11 月 26 日 14:24", the form the panels use for one completed turn. */
function monthDay(timestamp: number): string {
  if (!Number.isFinite(timestamp)) return "—";
  const parts = monthDayTime.formatToParts(timestamp);
  const part = (type: string) => parts.find((entry) => entry.type === type)?.value ?? "";
  return `${part("month")} 月 ${part("day")} 日 ${part("hour")}:${part("minute")}`;
}
const statuses = {
  initializing: "初始化", idle: "空闲", running: "运行中", error: "出错", closed: "已关闭",
};
const outcomes = { completed: "完成", failed: "失败", canceled: "取消" };

const count = formatTokenCount;
const duration = formatDurationMs;

/**
 * Two accent hues borrowed from the Agent Observatory palette: teal for the
 * cumulative cache reading, indigo for the latest sample. Light themes use
 * the darker text shade so both stay readable on surface1.
 */
const accents = {
  teal: { light: "#0D9488", lightText: "#0F766E", dark: "#2DD4BF" },
  indigo: { light: "#6366F1", lightText: "#4F46E5", dark: "#818CF8" },
} as const;
type Accent = keyof typeof accents;

/** Both cache headlines reserve the same block so their secondary metrics align. */
const CACHE_HEADLINE_MIN_HEIGHT = 64;

function darkTheme(colors: Colors): boolean {
  const hex = colors.surface0.replace("#", "");
  if (!/^[0-9a-f]{6}$/i.test(hex)) return true;
  const linear = (offset: number) => {
    const value = parseInt(hex.slice(offset, offset + 2), 16) / 255;
    return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  };
  // Same rule as the Observatory palette: compare against white and black.
  const luminance = 0.2126 * linear(0) + 0.7152 * linear(2) + 0.0722 * linear(4);
  return (luminance + 0.05) / 0.05 < 1.05 / (luminance + 0.05);
}

function withAlpha(color: string, alpha: number): string {
  return /^#[0-9a-f]{6}$/i.test(color)
    ? color + Math.round(alpha * 255).toString(16).padStart(2, "0")
    : color;
}

/** The percentage sign is its own type layer in the two cache headlines. */
function cacheRateParts(rate: number | null | undefined): { value: string; unit: string } {
  const text = formatCacheRate(rate);
  return text.endsWith("%") ? { value: text.slice(0, -1), unit: "%" } : { value: text, unit: "" };
}

/** `text` for the headline, `mark` for chips, `line`/`soft` for the card edges. */
function accent(colors: Colors, name: Accent, use: "mark" | "text" | "soft" | "line"): string {
  const dark = darkTheme(colors);
  const mark = dark ? accents[name].dark : accents[name].light;
  if (use === "mark") return mark;
  if (use === "text") return dark ? accents[name].dark : accents[name].lightText;
  if (use === "line") return withAlpha(mark, dark ? 0.55 : 0.4);
  return withAlpha(mark, dark ? 0.18 : 0.09);
}

/**
 * Labels and values share one wrapping four-up grid on desktop and two-up on
 * compact screens, matching the finalized panels. Values never clip: they wrap.
 */
function Metric({ label, value, unit, colors, valueSize = 17, basis }: {
  label: string;
  value: string;
  unit?: string;
  colors: Colors;
  valueSize?: number;
  basis: number;
}) {
  return (
    <View style={{ flexGrow: 1, flexShrink: 1, flexBasis: basis, minWidth: 0 }}>
      <Text style={{ color: colors.foregroundMuted, fontSize: 13, lineHeight: 18 }}>{label}</Text>
      <View style={{ flexDirection: "row", alignItems: "baseline", flexWrap: "wrap", columnGap: 3 }}>
        <Text
          style={{
            color: colors.foreground,
            fontSize: valueSize,
            lineHeight: valueSize + 6,
            fontWeight: "600",
            fontVariant: ["tabular-nums"],
          }}
        >
          {value}
        </Text>
        {unit ? <Text style={{ color: colors.foregroundMuted, fontSize: 13, fontWeight: "500" }}>{unit}</Text> : null}
      </View>
    </View>
  );
}

/** A headline value and its unit on separate type layers, never one long string. */
function Headline({ value, unit, tone, compact, emphasis = "primary", colors }: {
  value: string;
  unit: string;
  tone: string;
  compact: boolean;
  emphasis?: "primary" | "secondary";
  colors: Colors;
}) {
  const hasValue = value !== "—";
  const fontSize = emphasis === "primary" ? (compact ? 42 : 46) : 36;
  const lineHeight = Math.round(fontSize * 1.05);
  return (
    <View style={{ flexDirection: "row", alignItems: "baseline", flexWrap: "wrap", columnGap: 4, minHeight: CACHE_HEADLINE_MIN_HEIGHT }}>
      <Text
        style={{
          color: hasValue ? tone : colors.foregroundMuted,
          fontSize,
          fontWeight: "700",
          lineHeight,
          letterSpacing: -1.5,
          fontVariant: ["tabular-nums"],
        }}
      >
        {value}
      </Text>
      {hasValue ? <Text style={{ color: colors.foregroundMuted, fontSize: 21, fontWeight: "600" }}>{unit}</Text> : null}
    </View>
  );
}

/** One card component for both rows: an accent edge names the metric, the body keeps the theme surface. */
function Card({ title, tone, compact, children, colors }: {
  title: string;
  tone: Accent;
  compact: boolean;
  children: ReactNode;
  colors: Colors;
}) {
  return (
    <View
      style={{
        flexGrow: 1,
        flexShrink: 1,
        flexBasis: compact ? undefined : 300,
        minWidth: 0,
        alignSelf: "stretch",
        gap: compact ? 9 : 10,
        padding: compact ? 12 : 14,
        borderRadius: 12,
        borderWidth: 1,
        borderColor: accent(colors, tone, "line"),
        backgroundColor: colors.surface1,
      }}
    >
      <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
        <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: accent(colors, tone, "mark") }} />
        <Text style={{ flexShrink: 1, color: accent(colors, tone, "text"), fontSize: 16, lineHeight: 22, fontWeight: "600" }}>
          {title}
        </Text>
      </View>
      <View style={{ flexGrow: 1, gap: compact ? 10 : 12 }}>{children}</View>
    </View>
  );
}

/** A 4 px meter under each cache headline; width is the rate, never a fake value. */
function CacheMeter({ rate, tone, colors }: { rate: number | null; tone: Accent; colors: Colors }) {
  const width = rate === null ? 0 : Math.max(0, Math.min(100, rate * 100));
  return (
    <View style={{ height: 4, borderRadius: 10, backgroundColor: colors.surface2, overflow: "hidden" }}>
      <View style={{ height: "100%", width: `${width}%`, borderRadius: 10, backgroundColor: accent(colors, tone, "mark") }} />
    </View>
  );
}

/** The section bar used by "输出表现" and "会话": 18 px title, optional right-hand line. */
function SectionBar({ title, right, colors }: { title: string; right?: ReactNode; colors: Colors }) {
  return (
    <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
      <Text style={{ flexShrink: 1, color: colors.foreground, fontSize: 18, lineHeight: 24, fontWeight: "600" }}>{title}</Text>
      {right}
    </View>
  );
}

function TurnDetails({ agentRef, kind, workspaceId, cumulativeEnabled, scopeKey, scopeRevision, refreshRevision, compact, colors }: {
  agentRef: AgentRef;
  kind: "codex" | "claude" | null;
  workspaceId: string;
  cumulativeEnabled: boolean;
  scopeKey: string;
  scopeRevision: number;
  refreshRevision: number;
  compact: boolean;
  colors: Colors;
}) {
  const { status, measurement, observingTurn } = useLiveTurn(agentRef, kind === "claude");
  const codexTurn = useTurnOutput(
    agentRef,
    workspaceId,
    cumulativeEnabled,
    scopeKey,
    scopeRevision,
    refreshRevision,
    measurement?.turnId ?? null,
  );
  const lastText = measurement ? "最近完整观测的轮次 · " + outcomes[measurement.outcome] : null;
  const statusText = status === "unavailable" ? "实时事件连接不可用，收起后可重新打开。"
    : status === "connecting" ? "正在连接实时事件…"
    : observingTurn ? "正在观测当前轮次。"
    : lastText ? null : "打开详情后开始观测，下一次完整轮次结束后显示。";
  const data = codexTurn.data;
  const codexOutput = data?.outputTokens ?? null;
  const codexElapsed = data?.elapsedMs ?? null;
  const codexFirstToken = data?.firstTokenMs ?? null;
  const hasCodexTurn = cumulativeEnabled && (codexElapsed !== null || codexFirstToken !== null);
  const codexRate = tokensPerSecond(codexOutput, codexElapsed);
  const reason = data?.reason;
  const source = data?.source ?? kind;
  const native = source === "claude" ? "Claude" : "Codex";
  const basis = compact ? 132 : 120;
  const helper = { color: colors.foregroundMuted, fontSize: 13, lineHeight: 18 };

  return (
    <View style={{ gap: 10 }}>
      <Text style={{ color: colors.foreground, fontSize: 15, lineHeight: 21, fontWeight: "600" }}>Paseo 实时观测</Text>
      {statusText && <Text style={helper}>{statusText}</Text>}
      {lastText && <Text style={helper}>{lastText}</Text>}
      <View style={{ flexDirection: "row", flexWrap: "wrap", columnGap: 12, rowGap: 8 }}>
        <Metric label="Paseo 首个可见文本" value={duration(measurement?.firstVisibleMs)} colors={colors} basis={basis} />
        <Metric label="Paseo 整轮耗时" value={duration(measurement?.elapsedMs)} colors={colors} basis={basis} />
        <Metric
          label="本轮输出速率"
          value={formatTokenSpeed(measurement?.outputPerSecond, "full")}
          colors={colors}
          basis={basis}
        />
        {kind === "claude" && (
          <Metric
            label="Claude 上报首 Token"
            value={duration(measurement?.providerFirstTokenMs)}
            colors={colors}
            basis={basis}
          />
        )}
      </View>
      <Text style={helper}>
        首个可见文本取轮开始到首条非空白助手文本，不算工具或推理事件，也不是服务商 TTFT。整轮耗时含工具与等待；本轮输出速率仅在 Claude Code（含以 Claude 为底的自定义 provider）提供计数时显示；Claude 上报首 Token 取自 SDK 结果的 TTFT（0.1 秒精度），只在实时观测中可得，会话记录不保存。
      </Text>
      {codexTurn.isLoading && <Text style={helper}>正在读取最近 {native} 完成轮…</Text>}
      {hasCodexTurn && (
        <View style={{ gap: 8, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 9 }}>
          <Text style={{ color: colors.foreground, fontSize: 15, lineHeight: 21, fontWeight: "600" }}>最近 {native} 完成轮</Text>
          <View style={{ flexDirection: "row", flexWrap: "wrap", columnGap: 12, rowGap: 8 }}>
            <Metric label="整轮输出速率" value={formatTokenSpeed(codexRate, "full")} colors={colors} basis={basis} />
            {source !== "claude" && (
              <Metric
                label="Codex 首个模型 Token"
                value={duration(codexFirstToken)}
                colors={colors}
                basis={basis}
              />
            )}
            <Metric label="轮次边界耗时" value={duration(codexElapsed)} colors={colors} basis={basis} />
            <Metric
              label={source === "claude" ? "本轮输出 Token" : "累计输出差"}
              value={codexOutput === null ? "—" : count(codexOutput)}
              colors={colors}
              basis={basis}
            />
          </View>
          <Text style={helper}>
            {source === "claude"
              ? "取自 Claude 会话记录：从用户提问到 end_turn 回复的最后一条记录，输出为本轮各请求 output_tokens 之和，含工具与等待，不与实时观测混合。Claude 不记录首 Token。"
              : "首 Token 由 Codex 上报。耗时使用同一轮的原生边界，含工具与等待，不与实时观测混合。"}
          </Text>
          {codexOutput === null && <Text style={helper}>该轮缺少有效输出计数，速率留空。</Text>}
        </View>
      )}
      {!hasCodexTurn && !codexTurn.isLoading && reason === "missing-samples" && cumulativeEnabled && (
        <Text style={helper}>最近 {native} 完成轮缺少完整边界，输出与耗时留空。</Text>
      )}
      {cumulativeEnabled && !codexTurn.isLoading && (codexTurn.isError || reason === "read-failed") && (
        <Text style={helper}>最近 {native} 完成轮读取失败，留空。</Text>
      )}
    </View>
  );
}

function AgentRow({ agentRef, workspaceId, cumulativeEnabled, scopeKey, scopeRevision, refreshRevision, open, toggle, snapshot, cacheSample, compact, colors }: {
  agentRef: AgentRef;
  workspaceId: string;
  cumulativeEnabled: boolean;
  scopeKey: string;
  scopeRevision: number;
  refreshRevision: number;
  open: boolean;
  toggle: () => void;
  snapshot: UsageSnapshot | undefined;
  /** The row's latest cache sample: Codex from reported usage, Claude from its transcript. */
  cacheSample: CacheSample | null;
  compact: boolean;
  colors: Colors;
}) {
  const { id } = agentRef;
  const agent = useAgent(agentRef, ({ title, provider, model, status, updatedAt }) => ({
    title, provider, model, status, updatedAt,
  }));
  if (!agent) return null;
  const sample = cacheSample;
  const usage = snapshot?.usage;
  const updated = Date.parse(agent.updatedAt);
  const basis = compact ? 130 : 118;

  return (
    <View style={{ borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface1, borderRadius: 9 }}>
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ expanded: open }}
        onPress={toggle}
        style={{ paddingVertical: 9, paddingHorizontal: 12, gap: 3 }}
      >
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <Text style={{ flex: 1, minWidth: 0, color: colors.foreground, fontSize: 16, lineHeight: 22, fontWeight: "600" }}>
            {agent.title || "会话 " + id.slice(0, 8)}
          </Text>
          {sample ? (
            <View style={{ paddingHorizontal: 6, paddingVertical: 1, borderRadius: 5, backgroundColor: accent(colors, "teal", "soft") }}>
              <Text style={{ color: accent(colors, "teal", "text"), fontSize: 13, fontWeight: "600", fontVariant: ["tabular-nums"] }}>
                缓存 {formatCacheRate(sample.cached / sample.input)}
              </Text>
            </View>
          ) : null}
          <Text style={{ color: colors.foregroundMuted, fontSize: 14 }}>{open ? "收起" : "详情"}</Text>
          <View
            style={{
              width: 6,
              height: 6,
              marginTop: open ? 2 : -2,
              borderRightWidth: 1,
              borderBottomWidth: 1,
              borderColor: colors.foregroundMuted,
              transform: [{ rotate: open ? "225deg" : "45deg" }],
            }}
          />
        </View>
        <Text style={{ color: colors.foregroundMuted, fontSize: 14, lineHeight: 20 }}>
          {[agent.provider, agent.model, statuses[agent.status]].filter(Boolean).join(" · ")}
        </Text>
      </Pressable>
      {open && (
        <View style={{ padding: 12, borderTopWidth: 1, borderTopColor: colors.border, gap: 10 }}>
          <View style={{ flexDirection: "row", flexWrap: "wrap", columnGap: 8, rowGap: 8 }}>
            <Metric label="上报输入 Token" value={count(tokenCount(usage?.inputTokens))} colors={colors} basis={basis} />
            <Metric label="上报缓存读取" value={count(tokenCount(usage?.cachedInputTokens))} colors={colors} basis={basis} />
            <Metric label="上报输出 Token" value={count(tokenCount(usage?.outputTokens))} colors={colors} basis={basis} />
            <Metric
              label="上下文已用 / 上限"
              value={count(tokenCount(usage?.contextWindowUsedTokens)) + " / " + count(tokenCount(usage?.contextWindowMaxTokens))}
              colors={colors}
              basis={basis}
            />
          </View>
          <Text selectable style={{ color: colors.foregroundMuted, fontSize: 13, lineHeight: 18 }}>
            会话 ID {id} · 最近更新 {Number.isFinite(updated) ? dates.format(updated) : "—"}
          </Text>
          <View style={{ borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 9, gap: 8 }}>
            <TurnDetails
              agentRef={agentRef}
              kind={snapshot?.kind ?? null}
              workspaceId={workspaceId}
              cumulativeEnabled={cumulativeEnabled}
              scopeKey={scopeKey}
              scopeRevision={scopeRevision}
              refreshRevision={refreshRevision}
              compact={compact}
              colors={colors}
            />
          </View>
        </View>
      )}
    </View>
  );
}

type WorkspaceMetricsProps = Pick<PluginWorkspacePanelProps, "workspaceId" | "host" | "layout" | "theme">;

function WorkspaceMetrics({ workspaceId, host, layout, theme, sheet = false }: WorkspaceMetricsProps & { sheet?: boolean }) {
  const compact = sheet || layout.compact;
  const workspaceTitle = useWorkspace(workspaceId, (workspace) => workspace.title);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const refs = useAgents({
    hosts: [host.id],
    where: (agent) => agent.workspaceId === workspaceId && !agent.background,
    orderBy: ["createdAt", "desc"],
  });
  const query = useWorkspaceUsage(host.id, workspaceId, refs);
  const queryClient = useQueryClient();
  // The panel's own settings stream is what its turn details and gating follow.
  const shared = useSharedStore();
  const sharedScope = useSharedScope(shared);
  const sharedScopeStatus = useSharedScopeStatus(shared);
  const [localScope, setScope] = useState<WorkspaceScope | null>(null);
  const scope: WorkspaceScope | null = localScope ?? sharedScope;
  // A live shared scope is the runtime's current settings and wins, so an older
  // local copy cannot bypass it. While the shared scope is only pending or has
  // failed (its subscription closed), it is a placeholder: this panel's own
  // event is the real settings — both for its query and for the pill — and
  // must not be masked by it.
  const cumulativeScope: WorkspaceScope | null =
    resolveCumulativeScope(sharedScope, sharedScopeStatus, localScope);
  const [scopeRevision, setScopeRevision] = useState(0);
  // The manual refresh belongs to the shared store, so it bumps the one key the
  // composer pill also observes instead of only this panel's query.
  const settingsRevision = useSharedRevision(shared);
  const refreshRevision = useWorkspaceRevision(shared, workspaceId);
  // A rejected or closed subscription is never replayed by the host, so each
  // close opens a new one on the same backoff schedule as the composer pill.
  const [scopeAttempt, setScopeAttempt] = useState(0);
  const [scopeRetry] = useState(() => createSubscriptionRetry({
    schedule(callback, delayMs) {
      const timer = setTimeout(callback, delayMs);
      return { cancel: () => clearTimeout(timer) };
    },
    // A new attempt changes the subscription input, which makes the hook re-subscribe.
    retry: () => setScopeAttempt((attempt) => attempt + 1),
  }));
  const scopeSubscription = useSubscription(workspaceSettingsSubscription, { attempt: scopeAttempt }, (event) => {
    scopeRetry.opened();
    setScope(event);
    // While the shared scope is pending or its stream closed, hand this event
    // to the runtime as well. The runtime then has a scope even when its own
    // subscription never delivers, and the composer pill keys on the same one.
    publishPanelScope(shared, event);
    // Every settings event starts a fresh read. The per-agent turn keys carry
    // the local revision, so they are dropped. The cumulative key belongs to
    // the shared revision the runtime bumps on the same event, so the pill and
    // this panel move to the new key together — one query, one request.
    setScopeRevision((revision) => revision + 1);
    queryClient.removeQueries({ queryKey: ["workspace-metrics-turn"] });
  });
  useEffect(() => {
    if (scopeSubscription.status === "error" || scopeSubscription.status === "closed") scopeRetry.closed();
  }, [scopeRetry, scopeSubscription.status]);
  useEffect(() => () => scopeRetry.dispose(), [scopeRetry]);
  // Derived from the effective values, so a remount and a settings change that
  // leaves the same values map to the same query — and to the composer pill's.
  const scopeKey = scopeQueryKey(cumulativeScope);
  const cumulativeEnabled = cumulativeReadEnabled(cumulativeScope, workspaceId);
  const hub = useCumulativeHub();
  const cumulative = useCumulativeUsage(
    host.id,
    workspaceId,
    refs,
    cumulativeEnabled,
    scopeKey,
    settingsRevision,
    refreshRevision,
    hub,
    shared.refreshIntent(workspaceId, refreshRevision),
  );
  // Paseo's reported Claude usage has no cache-write count, so Claude
  // sessions take their newest request from the transcript instead.
  const claudeLatest = useMemo(() => {
    const map = new Map<string, CacheSample>();
    if (!cumulativeEnabled || cumulative.isPending || !cumulative.data || cumulative.data.error) return map;
    for (const entry of cumulative.data.latestSamples ?? []) {
      if (entry.input > 0 && entry.cached <= entry.input) map.set(entry.agentId, { input: entry.input, cached: entry.cached });
    }
    return map;
  }, [cumulativeEnabled, cumulative.isPending, cumulative.data]);
  const sampleFor = (id: string): CacheSample | null =>
    query.data?.get(id)?.cacheSample ?? claudeLatest.get(id) ?? null;
  const samples = refs.map(({ id }) => sampleFor(id));
  const claudeAgents = refs.filter(({ id }) => query.data?.get(id)?.kind === "claude").length;
  const totals = summarizeLatestSamples(samples);
  const colors = theme.colors;
  const recentPending = refs.length > 0 && query.isPending;
  const recentUnavailable = refs.length - (query.data?.size ?? 0);
  const scopePending = scope === null && scopeSubscription.status === "connecting";
  const scopeRequestFailed = scope === null &&
    (scopeSubscription.status === "error" || scopeSubscription.status === "closed");
  const scopeBlocked = scopeRequestFailed
    ? "累计范围读取失败，未读取。"
    : scope?.error
      ? "累计设置错误：" + scope.error + "，未读取。"
      : scope && !scope.enabled
        ? "累计统计已关闭。可在插件设置中开启。"
        : "累计未启用：本机允许列表不含此工作区，未读取。";
  const cumulativePending = cumulativeEnabled && refs.length > 0 && cumulative.isPending;
  const cumulativeError = cumulativeEnabled && cumulative.error ? "RPC 读取失败" : cumulative.data?.error ?? null;
  const hasCumulative = cumulativeEnabled && Boolean(cumulative.data) && !cumulativeError;
  const refreshing = query.isFetching || (cumulativeEnabled && cumulative.isFetching);
  const recentTurn = cumulative.data?.recentTurn ?? null;
  const turns = cumulative.data?.turns ?? null;
  const recentSpeed = recentTurn ? tokensPerSecond(recentTurn.outputTokens, recentTurn.elapsedMs) : null;
  const cumulativeSpeed = turns ? weightedTurnSpeed(turns) : null;
  const cumulativeFirstToken = turns ? averageFirstTokenMs(turns) : null;
  const blockedNote = scopePending
    ? "正在读取本机累计范围…"
    : !cumulativeEnabled
      ? scopeBlocked
      : cumulativeError
        ? "读取失败：" + cumulativeError + "，未按 0 计入"
        : null;
  const detail = (text: string) => hasCumulative && !cumulativePending ? text : "—";
  const cumulativeRate = hasCumulative && !cumulativePending ? cumulative.data?.rate ?? null : null;
  const cumulativeReady = cumulativeRate !== null;
  const recentRate = recentPending ? null : totals.rate;
  const cumulativeParts = cacheRateParts(cumulativeRate);
  const recentParts = cacheRateParts(recentRate);
  const cumulativeStatusNote = cumulativePending
    ? "正在读取累计缓存率…"
    : blockedNote
      ?? (refs.length === 0
        ? "当前工作区暂无可见会话"
        : hasCumulative
          ? "尚无有效累计缓存快照，未按 0 计入"
          : "累计数据尚未返回");
  const recentStatusNote = recentPending
    ? "正在读取最近缓存样本…"
    : refs.length === 0
      ? "当前工作区暂无可见会话"
      : totals.covered === 0
        ? "尚无有效最近缓存样本"
        : "取当前工作区内各可用会话的最近一次用量。";
  const recentCount = (value: number) =>
    !recentPending && totals.covered > 0 ? formatTokenCount(value) : "—";
  // Secondary speed figures drop the unit entirely when there is no reading.
  const speedText = (value: number | null) => value === null ? "—" : formatTokenSpeed(value);
  const splitSpeed = (value: number | null) => {
    const [number, ...unit] = detail(speedText(value)).split(" ");
    return { value: number, unit: unit.join(" ") };
  };
  const recentSpeedParts = splitSpeed(recentSpeed);
  const cumulativeSpeedParts = splitSpeed(cumulativeSpeed);
  const outputBlockedNote = scopePending
    ? "正在读取累计范围…"
    : !cumulativeEnabled
      ? scopeRequestFailed
        ? "累计范围读取失败"
        : scope?.error
          ? "累计设置错误"
          : scope && !scope.enabled
            ? "累计已关闭"
            : "累计未覆盖本工作区"
      : cumulativeError
        ? "累计读取失败"
        : null;
  const recentCompletedNote = hasCumulative && !cumulativePending && recentTurn
    ? "完成于 " + monthDay(recentTurn.completedAt)
    : outputBlockedNote
      ?? (refs.length === 0
        ? "当前工作区暂无可见会话"
        : cumulativePending
          ? "正在读取完成轮…"
          : "尚无可信完成轮");
  const cumulativeOutputNote = outputBlockedNote
    ?? (refs.length === 0
      ? "当前工作区暂无可见会话"
      : cumulativePending
        ? "正在读取累计用量…"
        : "按整轮耗时加权，包含工具与等待。");

  const refresh = () => {
    // Only this workspace's shared revision moves, so the pill and the panel
    // for this workspace refetch once while other workspaces keep their data.
    shared.bumpWorkspace(workspaceId, true);
    void query.refetch();
  };

  const styles = useMemo(() => {
    const helper = { color: colors.foregroundMuted, fontSize: 14, lineHeight: 20 };
    return {
      helper,
      small: { color: colors.foregroundMuted, fontSize: 13, lineHeight: 18 },
      grid: {
        flexDirection: compact ? ("column" as const) : ("row" as const),
        alignItems: "stretch" as const,
        gap: compact ? 8 : 12,
      },
      numbers: { flexDirection: "row" as const, flexWrap: "wrap" as const, columnGap: 8, rowGap: 8 },
      // Cache cards keep three figures on one line; the four-figure detail rows use
      // two columns once the panel is narrow, like the artboards.
      cacheBasis: compact ? 100 : 96,
      detailBasis: compact ? 160 : 96,
      refresh: {
        minHeight: 36,
        paddingVertical: 4,
        paddingHorizontal: 10,
        borderWidth: 1,
        borderColor: colors.border,
        borderRadius: 8,
        backgroundColor: colors.surface1,
      },
      refreshText: {
        color: refreshing ? colors.foregroundMuted : colors.accent,
        fontSize: 14,
        lineHeight: 20,
        fontWeight: "600" as const,
      },
    };
  }, [colors, compact, refreshing]);

  const cacheBasis = styles.cacheBasis;
  const detailBasis = styles.detailBasis;

  const cumulativeCard = (
    <Card title="累计缓存" tone="teal" compact={compact} colors={colors}>
      <View>
        {cumulativeReady ? (
          <Headline
            value={cumulativeParts.value}
            unit={cumulativeParts.unit}
            tone={accent(colors, "teal", "text")}
            compact={compact}
            emphasis="primary"
            colors={colors}
          />
        ) : (
          <Text style={[styles.helper, { minHeight: CACHE_HEADLINE_MIN_HEIGHT }]}>{cumulativeStatusNote}</Text>
        )}
      </View>
      {cumulativeReady ? <CacheMeter rate={cumulativeRate} tone="teal" colors={colors} /> : null}
      {hasCumulative && (
        <View style={styles.numbers}>
          <Metric label="缓存读取" value={detail(formatTokenCount(cumulative.data?.cachedInputTokens ?? null))} colors={colors} basis={cacheBasis} />
          <Metric label="总输入" value={detail(formatTokenCount(cumulative.data?.inputTokens ?? null))} colors={colors} basis={cacheBasis} />
          <Metric
            label="会话覆盖"
            value={hasCumulative ? cumulative.data?.covered + " / " + cumulative.data?.eligible : "—"}
            colors={colors}
            basis={cacheBasis}
          />
        </View>
      )}
      <View style={{ marginTop: "auto", gap: 4 }}>
        {hasCumulative && ((cumulative.data?.missing ?? 0) > 0 || (cumulative.data?.unavailable ?? 0) > 0) && (
          <>
            {(cumulative.data?.missing ?? 0) > 0 && (
              <Text style={styles.small}>
                {cumulative.data?.missing} 个符合条件会话缺少累计快照，未按 0 计入。
              </Text>
            )}
            {(cumulative.data?.unavailable ?? 0) > 0 && (
              <Text style={styles.small}>
                {cumulative.data?.unavailable} 个请求会话无法确认为当前工作区的 Codex 或 Claude 会话，已排除。
              </Text>
            )}
          </>
        )}
        {!cumulativeReady ? null : (
          <Text style={styles.helper}>按 Codex 累计快照与 Claude 会话记录汇总。</Text>
        )}
      </View>
    </Card>
  );

  const recentCard = (
    <Card title="最近样本缓存" tone="indigo" compact={compact} colors={colors}>
      <View>
        {recentRate !== null ? (
          <Headline
            value={recentParts.value}
            unit={recentParts.unit}
            tone={accent(colors, "indigo", "text")}
            compact={compact}
            emphasis={cumulativeReady ? "secondary" : "primary"}
            colors={colors}
          />
        ) : (
          <Text style={[styles.helper, { minHeight: CACHE_HEADLINE_MIN_HEIGHT }]}>{recentStatusNote}</Text>
        )}
      </View>
      {recentRate !== null ? <CacheMeter rate={recentRate} tone="indigo" colors={colors} /> : null}
      <View style={styles.numbers}>
        <Metric label="缓存读取" value={recentCount(totals.cached)} colors={colors} basis={cacheBasis} />
        <Metric label="总输入" value={recentCount(totals.input)} colors={colors} basis={cacheBasis} />
        <Metric
          label="会话覆盖"
          value={refs.length === 0 ? "—" : recentPending ? "读取中…" : totals.covered + " / " + refs.length}
          colors={colors}
          basis={cacheBasis}
        />
      </View>
      <View style={{ marginTop: "auto", gap: 4 }}>
        {!recentPending && recentUnavailable > 0 && (
          <Text style={styles.small}>{recentUnavailable} 个会话当前无法读取最近用量快照。</Text>
        )}
        {!recentPending && claudeAgents > 0 && !cumulativeEnabled && (
          <Text style={styles.small}>Claude 会话的最近样本取自会话记录，需开启累计统计后读取。</Text>
        )}
        <Text style={styles.helper}>{recentStatusNote}</Text>
      </View>
    </Card>
  );

  const recentOutputCard = (
    <Card title="最近完成轮" tone="indigo" compact={compact} colors={colors}>
      <View style={styles.numbers}>
        <Metric
          label="整轮输出速率"
          value={recentSpeedParts.value}
          unit={recentSpeedParts.unit}
          valueSize={18}
          colors={colors}
          basis={detailBasis}
        />
        <Metric label="首 Token" value={detail(formatDurationMs(recentTurn?.firstTokenMs ?? null))} colors={colors} basis={detailBasis} />
        <Metric label="整轮耗时" value={detail(formatDurationMs(recentTurn?.elapsedMs ?? null))} colors={colors} basis={detailBasis} />
        <Metric label="输出 Token" value={detail(formatTokenCount(recentTurn?.outputTokens ?? null))} colors={colors} basis={detailBasis} />
      </View>
      <View style={{ marginTop: "auto", gap: 4 }}>
        {cumulativeEnabled && hasCumulative && recentTurn && recentSpeed === null && (
          <Text style={styles.small}>该轮缺少有效输出计数或正向耗时，速率留空。</Text>
        )}
        <Text style={styles.helper}>{recentCompletedNote}</Text>
      </View>
    </Card>
  );

  const cumulativeOutputCard = (
    <Card title="累计整轮" tone="teal" compact={compact} colors={colors}>
      <View style={styles.numbers}>
        <Metric
          label="整轮输出速率"
          value={cumulativeSpeedParts.value}
          unit={cumulativeSpeedParts.unit}
          valueSize={18}
          colors={colors}
          basis={detailBasis}
        />
        <Metric label="平均首 Token" value={detail(formatDurationMs(cumulativeFirstToken))} colors={colors} basis={detailBasis} />
      </View>
      <Text style={styles.small}>
        {"完成轮 " + detail(formatTokenCount(turns?.completed ?? null))
          + " · 速率样本 " + detail(formatTokenCount(turns?.speedSamples ?? null))
          + " · 首 Token 样本 " + detail(formatTokenCount(turns?.firstTokenSamples ?? null))
          + " · 会话 " + detail(formatTokenCount(turns?.sessions ?? null))}
      </Text>
      <Text style={[styles.helper, { marginTop: "auto" }]}>{cumulativeOutputNote}</Text>
    </Card>
  );

  const content = (
    <>
      <View style={{ flexDirection: "row", alignItems: "center", gap: compact ? 10 : 13 }}>
        <View
          style={{
            width: compact ? 32 : 38,
            height: compact ? 32 : 38,
            borderRadius: 10,
            borderWidth: 1,
            borderColor: withAlpha(colors.accent, 0.55),
            backgroundColor: withAlpha(colors.accent, 0.12),
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <View style={{ flexDirection: "row", alignItems: "flex-end", gap: 3, height: 16 }}>
            <View style={{ width: 3, height: 7, borderRadius: 1, backgroundColor: colors.accent }} />
            <View style={{ width: 3, height: 11, borderRadius: 1, backgroundColor: colors.accent }} />
            <View style={{ width: 3, height: 16, borderRadius: 1, backgroundColor: colors.accent }} />
          </View>
        </View>
        <View style={{ flexShrink: 1, minWidth: 0 }}>
          <Text style={{ color: colors.foreground, fontSize: compact ? 23 : 25, lineHeight: compact ? 30 : 33, fontWeight: "700" }}>
            工作区用量
          </Text>
          <Text style={{ marginTop: 3, color: colors.foregroundMuted, fontSize: 14, lineHeight: 20 }}>
            {workspaceTitle ? workspaceTitle + " · 当前工作区" : "当前工作区"}
          </Text>
        </View>
      </View>
      <View style={styles.grid}>
        {cumulativeReady ? cumulativeCard : recentCard}
        {cumulativeReady ? recentCard : cumulativeCard}
      </View>
      <View style={{ gap: 8 }}>
        <SectionBar
          title="输出表现"
          colors={colors}
          right={refs.length > 0 ? (
            <Pressable
              accessibilityRole="button"
              accessibilityState={{ disabled: refreshing }}
              disabled={refreshing}
              onPress={refresh}
              style={styles.refresh}
            >
              <Text style={styles.refreshText}>{refreshing ? "正在读取…" : "刷新用量"}</Text>
            </Pressable>
          ) : undefined}
        />
        <View style={styles.grid}>
          {cumulativeReady ? cumulativeOutputCard : recentOutputCard}
          {cumulativeReady ? recentOutputCard : cumulativeOutputCard}
        </View>
      </View>
      <View style={{ gap: 8 }}>
        <SectionBar
          title="会话"
          colors={colors}
          right={<Text style={styles.helper}>{refs.length > 0 ? refs.length + " 个可见会话" : ""}</Text>}
        />
        {refs.length === 0 && <Text style={styles.helper}>当前工作区暂无可见会话。</Text>}
        <View style={{ gap: 6 }}>
          {refs.map((agentRef) => (
            <AgentRow
              key={agentRef.key}
              agentRef={agentRef}
              workspaceId={workspaceId}
              cumulativeEnabled={cumulativeEnabled}
              scopeKey={scopeKey}
              scopeRevision={scopeRevision}
              refreshRevision={refreshRevision}
              open={selectedId === agentRef.id}
              toggle={() => setSelectedId((current) => current === agentRef.id ? null : agentRef.id)}
              snapshot={query.data?.get(agentRef.id)}
              cacheSample={sampleFor(agentRef.id)}
              compact={compact}
              colors={colors}
            />
          ))}
        </View>
      </View>
    </>
  );

  // Paseo's sheet already scrolls the content. A nested ScrollView can hide lower sections.
  if (sheet) return <View style={{ gap: 14 }}>{content}</View>;

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.surface0 }}
      contentContainerStyle={{ paddingHorizontal: compact ? 14 : 32, paddingTop: compact ? 16 : 24, paddingBottom: compact ? 24 : 32, gap: compact ? 14 : 20 }}
    >
      {content}
    </ScrollView>
  );
}

export function MetricsPanel(props: PluginWorkspacePanelProps) {
  return <WorkspaceMetrics key={JSON.stringify([props.host.id, props.workspaceId])} {...props} />;
}

export function MetricsSheet(props: PluginButtonContentProps) {
  return <WorkspaceMetrics key={JSON.stringify([props.host.id, props.workspaceId])} {...props} sheet />;
}
