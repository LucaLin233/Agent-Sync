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

function Metric({ label, value, colors }: { label: string; value: string; colors: Colors }) {
  return (
    <View style={{ flexGrow: 1, flexBasis: 120, gap: 2 }}>
      <Text style={{ color: colors.foregroundMuted, fontSize: 12 }}>{label}</Text>
      <Text style={{ color: colors.foreground, fontSize: 17, fontWeight: "600", fontVariant: ["tabular-nums"] }}>{value}</Text>
    </View>
  );
}

/** The number is the subject: one headline value, then a quiet supporting row. */
function Headline({ label, value, note, colors }: {
  label: string;
  value: string;
  note?: string;
  colors: Colors;
}) {
  return (
    <View style={{ gap: 2 }}>
      <Text style={{ color: colors.foregroundMuted, fontSize: 12, letterSpacing: 0.4 }}>{label}</Text>
      <Text style={{ color: colors.foreground, fontSize: 30, fontWeight: "700", fontVariant: ["tabular-nums"] }}>{value}</Text>
      {note ? <Text style={{ color: colors.foregroundMuted, fontSize: 12 }}>{note}</Text> : null}
    </View>
  );
}

function Card({ title, children, colors }: { title: string; children: ReactNode; colors: Colors }) {
  return (
    <View style={{ gap: 10, padding: 14, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface1 }}>
      <Text style={{ color: colors.foregroundMuted, fontSize: 12, fontWeight: "600", letterSpacing: 0.6 }}>{title}</Text>
      {children}
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
        <View style={{ flexDirection: "row", justifyContent: "space-between", gap: 12 }}>
          <Text style={{ flex: 1, color: colors.foreground, fontWeight: "600" }}>{agent.title || "会话 " + id.slice(0, 8)}</Text>
          <Text style={{ color: colors.foregroundMuted }}>{open ? "收起" : "详情"}</Text>
        </View>
        <Text style={{ color: colors.foregroundMuted }}>
          {[agent.provider, agent.model, statuses[agent.status]].filter(Boolean).join(" · ")}
        </Text>
        <Text style={{ color: colors.foreground }}>
          {sample ? "最近缓存命中 " + formatCacheRate(sample.cached / sample.input) : "最近缓存命中 —"}
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
  const recentValue = hasCumulative && recentTurn && !cumulativePending ? formatTokenSpeed(recentSpeed, "full") : "—";
  const cumulativeValue = hasCumulative && turns && !cumulativePending ? formatTokenSpeed(cumulativeSpeed, "full") : "—";
  // The scope or read state is stated once, under both cards.
  const recentNote = blockedNote || cumulativePending ? undefined
    : recentTurn
      ? "完成于 " + (Number.isFinite(recentTurn.completedAt) ? dates.format(recentTurn.completedAt) : "—")
      : "尚无可信完成轮";
  const cumulativeNote = blockedNote || cumulativePending ? undefined
    : !turns || turns.completed === 0
      ? "尚无有效完成轮"
      : "按整轮耗时加权 · 速率样本 " + turns.speedSamples + " 轮";
  const detail = (text: string) => hasCumulative && !cumulativePending ? text : "—";

  const refresh = () => {
    setRefreshRevision((revision) => revision + 1);
    void query.refetch();
    if (cumulativeEnabled) void cumulative.refetch();
  };

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.surface0 }}
      contentContainerStyle={{ padding: layout.compact ? 12 : 20, gap: 12 }}
    >
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 12 }}>
        <View style={{ flexGrow: 1, flexBasis: 260, minWidth: 240 }}>
          <Card title="最近完成" colors={colors}>
            <Headline
              label="整轮输出速率"
              value={recentValue}
              note={recentNote}
              colors={colors}
            />
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 12 }}>
              <Metric label="首 Token" value={detail(formatDurationMs(recentTurn?.firstTokenMs ?? null))} colors={colors} />
              <Metric label="整轮耗时" value={detail(formatDurationMs(recentTurn?.elapsedMs ?? null))} colors={colors} />
              <Metric label="输出" value={detail(formatTokenCount(recentTurn?.outputTokens ?? null))} colors={colors} />
            </View>
            {cumulativeEnabled && hasCumulative && recentTurn && recentSpeed === null && (
              <Text style={{ color: colors.foregroundMuted, fontSize: 12 }}>
                该轮缺少有效输出计数或正向耗时，速率留空。
              </Text>
            )}
          </Card>
        </View>
        <View style={{ flexGrow: 1, flexBasis: 260, minWidth: 240 }}>
          <Card title="累计统计" colors={colors}>
            <Headline label="累计整轮输出速率" value={cumulativeValue} note={cumulativeNote} colors={colors} />
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 12 }}>
              <Metric label="平均首 Token" value={detail(formatDurationMs(cumulativeFirstToken))} colors={colors} />
              <Metric label="缓存率" value={formatCacheRate(hasCumulative ? cumulative.data?.rate ?? null : null)} colors={colors} />
              <Metric
                label="会话覆盖"
                value={hasCumulative ? cumulative.data?.covered + " / " + cumulative.data?.eligible : "—"}
                colors={colors}
              />
            </View>
            {hasCumulative && turns && turns.completed > 0 && (
              <Text style={{ color: colors.foregroundMuted, fontSize: 12 }}>
                {turns.sessions} 个会话 · {turns.completed} 个完成轮 · 首 Token 样本 {turns.firstTokenSamples}
              </Text>
            )}
          </Card>
        </View>
      </View>
      {(blockedNote || cumulativePending) && (
        <Text style={{ color: colors.foregroundMuted, fontSize: 12 }}>
          {blockedNote ?? "正在读取 Codex 累计用量…"}
        </Text>
      )}
      <View style={{ gap: 8, padding: 12, borderRadius: 10, backgroundColor: colors.surface1 }}>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 12 }}>
          <Metric label="最近样本缓存率" value={formatCacheRate(totals.rate)} colors={colors} />
          <Metric
            label="最近覆盖"
            value={recentPending ? "读取中…" : totals.covered + " / " + refs.length}
            colors={colors}
          />
          <Metric
            label="累计缓存读取"
            value={hasCumulative ? formatTokenCount(cumulative.data?.cachedInputTokens ?? null) : "—"}
            colors={colors}
          />
          <Metric
            label="累计总输入"
            value={hasCumulative ? formatTokenCount(cumulative.data?.inputTokens ?? null) : "—"}
            colors={colors}
          />
        </View>
        {hasCumulative && (cumulative.data?.missing ?? 0) > 0 && (
          <Text style={{ color: colors.foregroundMuted, fontSize: 12 }}>
            {cumulative.data?.missing} 个 Codex 会话缺少累计快照，未按 0 计入。
          </Text>
        )}
        {hasCumulative && (cumulative.data?.unavailable ?? 0) > 0 && (
          <Text style={{ color: colors.foregroundMuted, fontSize: 12 }}>
            {cumulative.data?.unavailable} 个请求会话无法确认为当前工作区的 Codex 会话，已排除。
          </Text>
        )}
        {totals.rate !== null && (
          <Text style={{ color: colors.foregroundMuted, fontSize: 12 }}>
            最近缓存读取 {formatTokenCount(totals.cached)} / 总输入 {formatTokenCount(totals.input)} token
          </Text>
        )}
        {!recentPending && recentUnavailable > 0 && (
          <Text style={{ color: colors.foregroundMuted, fontSize: 12 }}>
            {recentUnavailable} 个会话当前无法读取最近用量快照。
          </Text>
        )}
        <Text style={{ color: colors.foregroundMuted, fontSize: 12 }}>
          累计取每个唯一 native Codex 会话已观测到的成功完成轮，整轮耗时含工具与等待；最近样本缓存率另取各会话当前 lastUsage。
        </Text>
        {refs.length > 0 && (
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ disabled: refreshing }}
            disabled={refreshing}
            onPress={refresh}
            style={{ alignSelf: "flex-start", paddingVertical: 8 }}
          >
            <Text style={{ color: refreshing ? colors.foregroundMuted : colors.accent, fontWeight: "600" }}>
              {refreshing ? "正在读取…" : "刷新用量"}
            </Text>
          </Pressable>
        )}
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
