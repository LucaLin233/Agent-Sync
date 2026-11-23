import {
  type AgentRef,
  type PluginWorkspacePanelProps,
  useSubscription,
  useAgent,
  useAgents,
} from "@getpaseo/plugin/client";
import { useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Pressable, ScrollView, Text, View } from "react-native";
import {
  averageFirstTokenMs,
  formatCacheRate,
  formatDurationMs,
  formatTokenCount,
  formatTokenSpeed,
  summarizeLatestSamples,
  tokenCount,
  tokensPerSecond,
  weightedTurnSpeed,
} from "../shared/metrics";
import { workspaceInScope, workspaceSettingsSubscription, type WorkspaceScope } from "../shared/scope";
import { useCumulativeUsage } from "./use-cumulative";
import { useLiveTurn } from "./use-turn";
import { useTurnOutput } from "./use-turn-output";
import { useWorkspaceUsage, type UsageSnapshot } from "./use-usage";

type Colors = PluginWorkspacePanelProps["theme"]["colors"];
const dates = new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" });
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
const CACHE_HEADLINE_MIN_HEIGHT = 66;

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
 * Three compact indicators share one row down to a phone-width card. The
 * basis is small enough for 3-up and still wraps instead of clipping.
 */
function Metric({ label, value, unit, colors, basis = 68, valueSize = 15 }: {
  label: string;
  value: string;
  unit?: string;
  colors: Colors;
  basis?: number;
  valueSize?: number;
}) {
  return (
    <View style={{ flexGrow: 1, flexShrink: 1, flexBasis: basis, minWidth: 0, gap: 3 }}>
      <Text style={{ color: colors.foregroundMuted, fontSize: 11, lineHeight: 14 }}>{label}</Text>
      <View style={{ flexDirection: "row", alignItems: "baseline", flexWrap: "wrap", columnGap: 3 }}>
        <Text
          numberOfLines={2}
          style={{ color: colors.foreground, fontSize: valueSize, lineHeight: valueSize + 5, fontWeight: "600", fontVariant: ["tabular-nums"] }}
        >
          {value}
        </Text>
        {unit ? <Text style={{ color: colors.foregroundMuted, fontSize: 11, fontWeight: "500" }}>{unit}</Text> : null}
      </View>
    </View>
  );
}

/** A headline value and its unit on separate type layers, never one long string. */
function Headline({ label, value, unit, tone, emphasis = "primary", colors }: {
  label: string;
  value: string;
  unit: string;
  tone: string;
  emphasis?: "primary" | "secondary";
  colors: Colors;
}) {
  const hasValue = value !== "—";
  const fontSize = emphasis === "primary" ? 44 : 34;
  const lineHeight = emphasis === "primary" ? 48 : 39;
  const unitSize = emphasis === "primary" ? 20 : 16;
  return (
    <View style={{ gap: 3 }}>
      <Text style={{ color: colors.foregroundMuted, fontSize: 11, letterSpacing: 0.3 }}>{label}</Text>
      <View style={{ flexDirection: "row", alignItems: "baseline", flexWrap: "wrap", columnGap: 6 }}>
        <Text style={{ color: hasValue ? tone : colors.foregroundMuted, fontSize, fontWeight: "700", lineHeight, fontVariant: ["tabular-nums"] }}>
          {value}
        </Text>
        {hasValue ? <Text style={{ color: colors.foregroundMuted, fontSize: unitSize, fontWeight: "600" }}>{unit}</Text> : null}
      </View>
    </View>
  );
}

/** One card component for both rows: an accent edge names the metric, the body keeps the theme surface. */
function Card({ title, tone, children, colors }: {
  title: string;
  tone: Accent;
  children: ReactNode;
  colors: Colors;
}) {
  return (
    <View
      style={{
        flexGrow: 1,
        flexShrink: 1,
        flexBasis: 260,
        minWidth: 220,
        alignSelf: "stretch",
        gap: 12,
        padding: 14,
        borderRadius: 12,
        borderWidth: 1,
        borderColor: accent(colors, tone, "line"),
        backgroundColor: colors.surface1,
      }}
    >
      <View style={{ flexDirection: "row", alignItems: "center", gap: 7 }}>
        <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: accent(colors, tone, "mark") }} />
        <Text style={{ flexShrink: 1, color: accent(colors, tone, "text"), fontSize: 12, fontWeight: "700", letterSpacing: 0.4 }}>{title}</Text>
      </View>
      <View style={{ flexGrow: 1, gap: 12 }}>{children}</View>
    </View>
  );
}

function TurnDetails({ agentRef, workspaceId, cumulativeEnabled, scopeKey, scopeRevision, refreshRevision, colors }: {
  agentRef: AgentRef;
  workspaceId: string;
  cumulativeEnabled: boolean;
  scopeKey: string;
  scopeRevision: number;
  refreshRevision: number;
  colors: Colors;
}) {
  const { status, measurement, observingTurn } = useLiveTurn(agentRef);
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
    : lastText ? null : "打开详情后开始观测，从下一次完整轮次起显示。";
  const data = codexTurn.data;
  const codexOutput = data?.outputTokens ?? null;
  const codexElapsed = data?.elapsedMs ?? null;
  const codexFirstToken = data?.firstTokenMs ?? null;
  const hasCodexTurn = cumulativeEnabled && (codexElapsed !== null || codexFirstToken !== null);
  const codexRate = tokensPerSecond(codexOutput, codexElapsed);
  const reason = data?.reason;

  return (
    <View style={{ gap: 8 }}>
      {statusText && <Text style={{ color: colors.foregroundMuted }}>{statusText}</Text>}
      {lastText && <Text style={{ color: colors.foregroundMuted }}>{lastText}</Text>}
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 12 }}>
        <Metric label="Paseo 首个可见文本" value={duration(measurement?.firstVisibleMs)} colors={colors} />
        <Metric label="Paseo 整轮耗时" value={duration(measurement?.elapsedMs)} colors={colors} />
        <Metric
          label="本轮输出速率"
          value={formatTokenSpeed(measurement?.outputPerSecond, "full")}
          colors={colors}
        />
      </View>
      <Text style={{ color: colors.foregroundMuted, fontSize: 12 }}>
        首个可见文本取轮开始到首条非空白助手文本，不算工具或推理事件，也不是服务商 TTFT。整轮耗时含工具与等待；本轮输出速率仅在内置 Claude Code 提供计数时显示。
      </Text>
      {codexTurn.isLoading && (
        <Text style={{ color: colors.foregroundMuted, fontSize: 12 }}>正在读取最近 Codex 完成轮…</Text>
      )}
      {hasCodexTurn && (
        <View style={{ gap: 4 }}>
          <Text style={{ color: colors.foregroundMuted, fontWeight: "600" }}>最近 Codex 完成轮</Text>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 12 }}>
            <Metric label="累计输出差" value={codexOutput === null ? "—" : count(codexOutput) + " token"} colors={colors} />
            <Metric label="轮次边界耗时" value={duration(codexElapsed)} colors={colors} />
            {codexFirstToken !== null && (
              <Metric label="Codex 首个模型 Token" value={duration(codexFirstToken)} colors={colors} />
            )}
            <Metric
              label="整轮输出速率"
              value={formatTokenSpeed(codexRate, "full")}
              colors={colors}
            />
          </View>
          <Text style={{ color: colors.foregroundMuted, fontSize: 12 }}>
            取自该会话完成轮的原生边界与累计输出差，含工具与等待，不与上方实时观测混合；首 token 为 Codex 自报。
          </Text>
          {codexOutput === null && (
            <Text style={{ color: colors.foregroundMuted, fontSize: 12 }}>
              该轮缺少有效输出计数，速率留空。
            </Text>
          )}
        </View>
      )}
      {!hasCodexTurn && !codexTurn.isLoading && reason === "missing-samples" && cumulativeEnabled && (
        <Text style={{ color: colors.foregroundMuted, fontSize: 12 }}>
          最近 Codex 完成轮缺少完整边界，输出与耗时留空。
        </Text>
      )}
      {cumulativeEnabled && !codexTurn.isLoading && (codexTurn.isError || reason === "read-failed") && (
        <Text style={{ color: colors.foregroundMuted, fontSize: 12 }}>
          最近 Codex 完成轮读取失败，留空。
        </Text>
      )}
    </View>
  );
}

function AgentRow({ agentRef, workspaceId, cumulativeEnabled, scopeKey, scopeRevision, refreshRevision, open, toggle, snapshot, colors }: {
  agentRef: AgentRef;
  workspaceId: string;
  cumulativeEnabled: boolean;
  scopeKey: string;
  scopeRevision: number;
  refreshRevision: number;
  open: boolean;
  toggle: () => void;
  snapshot: UsageSnapshot | undefined;
  colors: Colors;
}) {
  const { id } = agentRef;
  const agent = useAgent(agentRef, ({ title, provider, model, status, updatedAt }) => ({
    title, provider, model, status, updatedAt,
  }));
  if (!agent) return null;
  const sample = snapshot?.cacheSample;
  const usage = snapshot?.usage;
  const updated = Date.parse(agent.updatedAt);

  return (
    <View style={{ borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface1, borderRadius: 10 }}>
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ expanded: open }}
        onPress={toggle}
        style={{ padding: 12, gap: 5 }}
      >
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <Text numberOfLines={1} style={{ flex: 1, color: colors.foreground, fontWeight: "600" }}>
            {agent.title || "会话 " + id.slice(0, 8)}
          </Text>
          {sample ? (
            <View style={{ paddingHorizontal: 7, paddingVertical: 2, borderRadius: 6, backgroundColor: accent(colors, "teal", "soft") }}>
              <Text style={{ color: accent(colors, "teal", "text"), fontSize: 11, fontWeight: "700", fontVariant: ["tabular-nums"] }}>
                缓存 {formatCacheRate(sample.cached / sample.input)}
              </Text>
            </View>
          ) : null}
          <Text style={{ color: colors.foregroundMuted, fontSize: 12 }}>{open ? "收起" : "详情"}</Text>
        </View>
        <Text numberOfLines={1} style={{ color: colors.foregroundMuted, fontSize: 12 }}>
          {[agent.provider, agent.model, statuses[agent.status]].filter(Boolean).join(" · ")}
        </Text>
      </Pressable>
      {open && (
        <View style={{ padding: 12, borderTopWidth: 1, borderColor: colors.border, gap: 12 }}>
          <Text selectable style={{ color: colors.foregroundMuted }}>会话 ID {id}</Text>
          <Text style={{ color: colors.foregroundMuted }}>
            最近更新 {Number.isFinite(updated) ? dates.format(updated) : "—"}
          </Text>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 12 }}>
            <Metric label="上报输入 Token" value={count(tokenCount(usage?.inputTokens))} colors={colors} />
            <Metric label="上报缓存读取" value={count(tokenCount(usage?.cachedInputTokens))} colors={colors} />
            <Metric label="上报输出 Token" value={count(tokenCount(usage?.outputTokens))} colors={colors} />
            <Metric label="上下文已用 / 上限" value={count(tokenCount(usage?.contextWindowUsedTokens)) + " / " + count(tokenCount(usage?.contextWindowMaxTokens))} colors={colors} />
          </View>
          <TurnDetails
            agentRef={agentRef}
            workspaceId={workspaceId}
            cumulativeEnabled={cumulativeEnabled}
            scopeKey={scopeKey}
            scopeRevision={scopeRevision}
            refreshRevision={refreshRevision}
            colors={colors}
          />
        </View>
      )}
    </View>
  );
}

function WorkspaceMetrics({ workspaceId, host, layout, theme }: PluginWorkspacePanelProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const refs = useAgents({
    hosts: [host.id],
    where: (agent) => agent.workspaceId === workspaceId && !agent.background,
    orderBy: ["createdAt", "desc"],
  });
  const query = useWorkspaceUsage(host.id, workspaceId, refs);
  const queryClient = useQueryClient();
  const [scope, setScope] = useState<WorkspaceScope | null>(null);
  const [scopeRevision, setScopeRevision] = useState(0);
  const [refreshRevision, setRefreshRevision] = useState(0);
  const scopeSubscription = useSubscription(workspaceSettingsSubscription, {}, (event) => {
    setScope(event);
    // Every settings event starts a fresh read: the scope projection can be
    // identical (for example, a changed Codex home), so the revision is part of
    // the keys. Clearing first also prevents a remount from reusing old data.
    setScopeRevision((revision) => revision + 1);
    queryClient.removeQueries({ queryKey: ["workspace-metrics-cumulative"] });
    queryClient.removeQueries({ queryKey: ["workspace-metrics-turn"] });
  });
  // Derived from the effective values, so a remount and a settings change that
  // leaves the same values map to the same query.
  const scopeKey = scope
    ? [scope.enabled, scope.allWorkspaces, [...scope.workspaceIds].sort().join(","), scope.error ?? ""].join("|")
    : "pending";
  const cumulativeEnabled = scope !== null && workspaceInScope(scope, workspaceId);
  const cumulative = useCumulativeUsage(
    workspaceId,
    refs,
    cumulativeEnabled,
    scopeKey,
    scopeRevision,
    refreshRevision,
  );
  const samples = refs.map(({ id }) => query.data?.get(id)?.cacheSample ?? null);
  const totals = summarizeLatestSamples(samples);
  const colors = theme.colors;
  const recentPending = refs.length > 0 && query.isPending;
  const recentUnavailable = refs.length - (query.data?.size ?? 0);
  const scopePending = scope === null && scopeSubscription.status === "connecting";
  const scopeRequestFailed = scope === null &&
    (scopeSubscription.status === "error" || scopeSubscription.status === "closed");
  const scopeBlocked = scopeRequestFailed
    ? "累计范围读取失败"
    : scope?.error
      ? "累计设置错误：" + scope.error
      : scope && !scope.enabled
        ? "累计统计已关闭"
        : "累计未启用：本机允许列表不含此 workspace";
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
      ? scopeBlocked + "，未读取"
      : cumulativeError
        ? "读取失败：" + cumulativeError + "，未按 0 计入"
        : null;
  const detail = (text: string) => hasCumulative && !cumulativePending ? text : "—";
  // Cache is the headline. The cumulative reading only leads when it has a real
  // rate; otherwise the recent sample becomes the first and largest card.
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
        : "取各会话最近一次用量";
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
  // The cache cards already state the full reason; keep these footers short.
  const outputBlockedNote = scopePending
    ? "正在读取累计范围…"
    : !cumulativeEnabled
      ? scopeRequestFailed
        ? "累计范围读取失败"
        : scope?.error
          ? "累计设置错误"
          : scope && !scope.enabled
            ? "累计已关闭"
            : "不在累计范围"
      : cumulativeError
        ? "累计读取失败"
        : null;
  const recentCompletedNote = hasCumulative && !cumulativePending && recentTurn
    ? "完成于 " + (Number.isFinite(recentTurn.completedAt) ? dates.format(recentTurn.completedAt) : "—")
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
        ? "正在读取 Codex 累计用量…"
        : "按整轮耗时加权，包含工具与等待。");

  const refresh = () => {
    setRefreshRevision((revision) => revision + 1);
    void query.refetch();
    if (cumulativeEnabled) void cumulative.refetch();
  };

  const cumulativeCard = (
    <Card title="累计缓存" tone="teal" colors={colors}>
      <View style={{ minHeight: CACHE_HEADLINE_MIN_HEIGHT }}>
        {cumulativeReady ? (
          <Headline
            label="累计缓存率"
            value={cumulativeParts.value}
            unit={cumulativeParts.unit}
            tone={accent(colors, "teal", "text")}
            emphasis="primary"
            colors={colors}
          />
        ) : (
          <Text style={{ color: colors.foregroundMuted, fontSize: 13, lineHeight: 19 }}>
            {cumulativeStatusNote}
          </Text>
        )}
      </View>
      {hasCumulative && (
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 10 }}>
          <Metric label="缓存读取" value={detail(formatTokenCount(cumulative.data?.cachedInputTokens ?? null))} colors={colors} basis={90} />
          <Metric label="总输入" value={detail(formatTokenCount(cumulative.data?.inputTokens ?? null))} colors={colors} basis={90} />
          <Metric
            label="会话覆盖"
            value={hasCumulative ? cumulative.data?.covered + " / " + cumulative.data?.eligible : "—"}
            colors={colors}
            basis={90}
          />
        </View>
      )}
      {hasCumulative && ((cumulative.data?.missing ?? 0) > 0 || (cumulative.data?.unavailable ?? 0) > 0) && (
        <View style={{ marginTop: "auto", gap: 4 }}>
          {(cumulative.data?.missing ?? 0) > 0 && (
            <Text style={{ color: colors.foregroundMuted, fontSize: 12 }}>
              {cumulative.data?.missing} 个 Codex 会话缺少累计快照，未按 0 计入。
            </Text>
          )}
          {(cumulative.data?.unavailable ?? 0) > 0 && (
            <Text style={{ color: colors.foregroundMuted, fontSize: 12 }}>
              {cumulative.data?.unavailable} 个请求会话无法确认为当前工作区的 Codex 会话，已排除。
            </Text>
          )}
        </View>
      )}
    </Card>
  );

  const recentCard = (
    <Card title="最近样本缓存" tone="indigo" colors={colors}>
      <View style={{ minHeight: CACHE_HEADLINE_MIN_HEIGHT }}>
        {recentRate !== null ? (
          <Headline
            label="最近样本缓存率"
            value={recentParts.value}
            unit={recentParts.unit}
            tone={accent(colors, "indigo", "text")}
            emphasis={cumulativeReady ? "secondary" : "primary"}
            colors={colors}
          />
        ) : (
          <Text style={{ color: colors.foreground, fontSize: 15, lineHeight: 21, fontWeight: "600" }}>
            {recentParts.value}
          </Text>
        )}
      </View>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 10 }}>
        <Metric label="缓存读取" value={recentCount(totals.cached)} colors={colors} basis={90} />
        <Metric label="总输入" value={recentCount(totals.input)} colors={colors} basis={90} />
        <Metric
          label="会话覆盖"
          value={refs.length === 0 ? "—" : recentPending ? "读取中…" : totals.covered + " / " + refs.length}
          colors={colors}
          basis={90}
        />
      </View>
      <View style={{ marginTop: "auto", gap: 4 }}>
        {!recentPending && recentUnavailable > 0 && (
          <Text style={{ color: colors.foregroundMuted, fontSize: 12 }}>
            {recentUnavailable} 个会话当前无法读取最近用量快照。
          </Text>
        )}
        <Text style={{ color: colors.foregroundMuted, fontSize: 12 }}>{recentStatusNote}</Text>
      </View>
    </Card>
  );

  const recentOutputCard = (
    <Card title="最近完成轮" tone="indigo" colors={colors}>
      <View style={{ flexDirection: "row", flexWrap: "wrap", columnGap: 12, rowGap: 6 }}>
        <Metric
          label="整轮输出速率"
          value={recentSpeedParts.value}
          unit={recentSpeedParts.unit}
          valueSize={21}
          colors={colors}
          basis={92}
        />
        <Metric
          label="首 Token"
          value={detail(formatDurationMs(recentTurn?.firstTokenMs ?? null))}
          colors={colors}
          basis={82}
        />
      </View>
      <View style={{ flexDirection: "row", flexWrap: "wrap", columnGap: 12, rowGap: 6 }}>
        <Metric label="整轮耗时" value={detail(formatDurationMs(recentTurn?.elapsedMs ?? null))} colors={colors} basis={82} />
        <Metric label="输出" value={detail(formatTokenCount(recentTurn?.outputTokens ?? null))} colors={colors} basis={82} />
      </View>
      <View style={{ marginTop: "auto", gap: 4 }}>
        {cumulativeEnabled && hasCumulative && recentTurn && recentSpeed === null && (
          <Text style={{ color: colors.foregroundMuted, fontSize: 11, lineHeight: 15 }}>
            该轮缺少有效输出计数或正向耗时，速率留空。
          </Text>
        )}
        <Text style={{ color: colors.foregroundMuted, fontSize: 11, lineHeight: 15 }}>{recentCompletedNote}</Text>
      </View>
    </Card>
  );

  const cumulativeOutputCard = (
    <Card title="累计整轮" tone="teal" colors={colors}>
      <View style={{ flexDirection: "row", flexWrap: "wrap", columnGap: 12, rowGap: 6 }}>
        <Metric
          label="累计整轮速率"
          value={cumulativeSpeedParts.value}
          unit={cumulativeSpeedParts.unit}
          valueSize={21}
          colors={colors}
          basis={92}
        />
        <Metric
          label="平均首 Token"
          value={detail(formatDurationMs(cumulativeFirstToken))}
          colors={colors}
          basis={82}
        />
      </View>
      <Text style={{ color: colors.foregroundMuted, fontSize: 11, lineHeight: 15, fontVariant: ["tabular-nums"] }}>
        {"完成轮 " + detail(formatTokenCount(turns?.completed ?? null))
          + " · 速率样本 " + detail(formatTokenCount(turns?.speedSamples ?? null))
          + " · 首 Token 样本 " + detail(formatTokenCount(turns?.firstTokenSamples ?? null))
          + " · 会话 " + detail(formatTokenCount(turns?.sessions ?? null))}
      </Text>
      <Text style={{ marginTop: "auto", color: colors.foregroundMuted, fontSize: 11, lineHeight: 15 }}>{cumulativeOutputNote}</Text>
    </Card>
  );

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.surface0 }}
      contentContainerStyle={{ padding: layout.compact ? 12 : 20, gap: 12 }}
    >
      <View style={{ flexDirection: "row", flexWrap: "wrap", alignItems: "stretch", gap: 12 }}>
        {cumulativeReady ? cumulativeCard : recentCard}
        {cumulativeReady ? recentCard : cumulativeCard}
      </View>
      <View style={{ gap: 10 }}>
        <View style={{ flexDirection: "row", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 7 }}>
            <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: colors.border }} />
            <Text style={{ color: colors.foreground, fontSize: 12, fontWeight: "700", letterSpacing: 0.4 }}>输出表现</Text>
          </View>
          {refs.length > 0 && (
            <Pressable
              accessibilityRole="button"
              accessibilityState={{ disabled: refreshing }}
              disabled={refreshing}
              onPress={refresh}
              style={{ paddingVertical: 4 }}
            >
              <Text style={{ color: refreshing ? colors.foregroundMuted : colors.accent, fontSize: 12, fontWeight: "600" }}>
                {refreshing ? "正在读取…" : "刷新用量"}
              </Text>
            </Pressable>
          )}
        </View>
        <View style={{ flexDirection: "row", flexWrap: "wrap", alignItems: "stretch", gap: 12 }}>
          {cumulativeReady ? cumulativeOutputCard : recentOutputCard}
          {cumulativeReady ? recentOutputCard : cumulativeOutputCard}
        </View>
      </View>
      {refs.length === 0 && <Text style={{ color: colors.foregroundMuted }}>当前工作区暂无可见会话。</Text>}
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
          colors={colors}
        />
      ))}
    </ScrollView>
  );
}

export function MetricsPanel(props: PluginWorkspacePanelProps) {
  return <WorkspaceMetrics key={JSON.stringify([props.host.id, props.workspaceId])} {...props} />;
}
