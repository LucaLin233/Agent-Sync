import {
  type AgentRef,
  type PluginWorkspacePanelProps,
  useSubscription,
  useAgent,
  useAgents,
} from "@getpaseo/plugin/client";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Pressable, ScrollView, Text, View } from "react-native";
import { formatCacheRate, summarizeLatestSamples, tokenCount } from "../shared/metrics";
import { workspaceInScope, workspaceSettingsSubscription, type WorkspaceScope } from "../shared/scope";
import { useCumulativeUsage } from "./use-cumulative";
import { useLiveTurn } from "./use-turn";
import { useTurnOutput } from "./use-turn-output";
import { useWorkspaceUsage, type UsageSnapshot } from "./use-usage";

type Colors = PluginWorkspacePanelProps["theme"]["colors"];
const counts = new Intl.NumberFormat("zh-CN");
const decimal = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 });
const dates = new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" });
const statuses = {
  initializing: "初始化", idle: "空闲", running: "运行中", error: "出错", closed: "已关闭",
};
const outcomes = { completed: "完成", failed: "失败", canceled: "取消" };

function count(value: number | null) {
  return value === null ? "—" : counts.format(value);
}

function duration(ms: number | null | undefined) {
  if (ms === null || ms === undefined) return "—";
  return ms < 1_000 ? counts.format(ms) + " ms" : decimal.format(ms / 1_000) + " 秒";
}

function Metric({ label, value, colors }: { label: string; value: string; colors: Colors }) {
  return (
    <View style={{ flexGrow: 1, flexBasis: 125, gap: 4 }}>
      <Text style={{ color: colors.foregroundMuted, fontSize: 13 }}>{label}</Text>
      <Text style={{ color: colors.foreground, fontSize: 18, fontWeight: "600" }}>{value}</Text>
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
  const codexRate = codexOutput !== null && codexElapsed !== null && codexElapsed > 0
    ? codexOutput * 1_000 / codexElapsed
    : null;
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
          value={measurement?.outputPerSecond == null
            ? "—"
            : decimal.format(measurement.outputPerSecond) + " token/s"}
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
              value={codexRate === null ? "—" : decimal.format(codexRate) + " token/s"}
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
  const cumulative = useCumulativeUsage(workspaceId, refs, cumulativeEnabled, scopeKey, scopeRevision);
  const samples = refs.map(({ id }) => query.data?.get(id)?.cacheSample ?? null);
  const totals = summarizeLatestSamples(samples);
  const colors = theme.colors;
  const recentPending = refs.length > 0 && query.isPending;
  const recentUnavailable = refs.length - (query.data?.size ?? 0);
  const scopePending = scope === null && scopeSubscription.status === "connecting";
  const scopeRequestFailed = scope === null &&
    (scopeSubscription.status === "error" || scopeSubscription.status === "closed");
  const scopeError = scopeRequestFailed ? "设置订阅不可用" : scope?.error ?? null;
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
  const cumulativeValue = (value: string) => {
    if (scopePending) return "读取中…";
    if (scopeError || !cumulativeEnabled) return "未启用";
    if (cumulativePending) return "读取中…";
    return value;
  };
  const refreshing = query.isFetching || (cumulativeEnabled && cumulative.isFetching);

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
      <View style={{ gap: 8, padding: 12, borderRadius: 10, backgroundColor: colors.surface1 }}>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 12 }}>
          <Metric
            label="累计缓存率"
            value={cumulativeValue(formatCacheRate(hasCumulative ? cumulative.data?.rate ?? null : null))}
            colors={colors}
          />
          <Metric
            label="累计覆盖"
            value={cumulativeValue(hasCumulative ? cumulative.data?.covered + " / " + cumulative.data?.eligible : "—")}
            colors={colors}
          />
          <Metric label="最近样本缓存率" value={formatCacheRate(totals.rate)} colors={colors} />
          <Metric
            label="最近覆盖"
            value={recentPending ? "读取中…" : totals.covered + " / " + refs.length}
            colors={colors}
          />
        </View>
        {scopePending && (
          <Text style={{ color: colors.foregroundMuted, fontSize: 13 }}>正在读取本机累计范围…</Text>
        )}
        {!scopePending && (scopeError || !cumulativeEnabled) && (
          <Text style={{ color: colors.foregroundMuted, fontSize: 13 }}>
            {scopeBlocked}，以下仅显示最近样本。
          </Text>
        )}
        {cumulativeEnabled && cumulativeError && (
          <Text style={{ color: colors.foregroundMuted, fontSize: 13 }}>
            累计缓存率不可用：{cumulativeError}。不会按 0 计入。
          </Text>
        )}
        {cumulativePending && !cumulativeError && (
          <Text style={{ color: colors.foregroundMuted, fontSize: 13 }}>正在读取 Codex 累计用量…</Text>
        )}
        {hasCumulative && (
          <>
            <Text style={{ color: colors.foregroundMuted, fontSize: 13 }}>
              累计缓存读取 {count(cumulative.data?.cachedInputTokens ?? null)} / 总输入 {count(cumulative.data?.inputTokens ?? null)} token
            </Text>
            {(cumulative.data?.missing ?? 0) > 0 && (
              <Text style={{ color: colors.foregroundMuted, fontSize: 13 }}>
                {cumulative.data?.missing} 个 Codex 会话缺少累计快照，未按 0 计入。
              </Text>
            )}
            {(cumulative.data?.unavailable ?? 0) > 0 && (
              <Text style={{ color: colors.foregroundMuted, fontSize: 13 }}>
                {cumulative.data?.unavailable} 个请求会话无法确认为当前工作区的 Codex 会话，已排除。
              </Text>
            )}
          </>
        )}
        <Text style={{ color: colors.foregroundMuted, fontSize: 13 }}>
          累计取每个唯一 native Codex 会话最后一笔 total_token_usage；最近样本另取各会话当前 lastUsage，两者时点可能不同。
        </Text>
        {totals.rate !== null && (
          <Text style={{ color: colors.foregroundMuted, fontSize: 13 }}>
            最近缓存读取 {count(totals.cached)} / 总输入 {count(totals.input)} token
          </Text>
        )}
        {!recentPending && recentUnavailable > 0 && (
          <Text style={{ color: colors.foregroundMuted, fontSize: 13 }}>
            {recentUnavailable} 个会话当前无法读取最近用量快照。
          </Text>
        )}
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
