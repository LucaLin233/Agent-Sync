import {
  type AgentRef,
  type PluginWorkspacePanelProps,
  useAgent,
  useAgents,
} from "@getpaseo/plugin/client";
import { useState } from "react";
import { Pressable, ScrollView, Text, View } from "react-native";
import { formatCacheRate, summarizeLatestSamples, tokenCount } from "../shared/metrics";
import { useLiveTurn } from "./use-turn";
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

function TurnDetails({ agentRef, colors }: { agentRef: AgentRef; colors: Colors }) {
  const { status, measurement, observingTurn } = useLiveTurn(agentRef);
  const lastText = measurement ? "最近完整观测的轮次 · " + outcomes[measurement.outcome] : null;
  const statusText = status === "unavailable" ? "实时事件连接不可用，收起后可重新打开。"
    : status === "connecting" ? "正在连接实时事件…"
    : observingTurn ? "正在观测当前轮次。"
    : lastText ? null : "打开详情后开始观测，从下一次完整轮次起显示。";

  return (
    <View style={{ gap: 8 }}>
      {statusText && <Text style={{ color: colors.foregroundMuted }}>{statusText}</Text>}
      {lastText && <Text style={{ color: colors.foregroundMuted }}>{lastText}</Text>}
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 12 }}>
        <Metric label="Paseo 首段观测" value={duration(measurement?.firstAssistantMs)} colors={colors} />
        <Metric label="Paseo 整轮耗时" value={duration(measurement?.elapsedMs)} colors={colors} />
        <Metric
          label="整轮输出速率"
          value={measurement?.outputPerSecond == null ? "—" : decimal.format(measurement.outputPerSecond) + " token/s"}
          colors={colors}
        />
      </View>
      <Text style={{ color: colors.foregroundMuted, fontSize: 12 }}>
        首段取首个助手消息事件。整轮速率适用于内置 Claude Code 提供输出计数的成功轮次，计时包含工具和等待。服务商首字延迟与生成 TPS 未上报。
      </Text>
    </View>
  );
}

function AgentRow({ agentRef, open, toggle, snapshot, colors }: {
  agentRef: AgentRef;
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
          <TurnDetails agentRef={agentRef} colors={colors} />
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
  const samples = refs.map(({ id }) => query.data?.get(id)?.cacheSample ?? null);
  const totals = summarizeLatestSamples(samples);
  const colors = theme.colors;
  const pending = refs.length > 0 && query.isPending;
  const unavailable = refs.length - (query.data?.size ?? 0);

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.surface0 }}
      contentContainerStyle={{ padding: layout.compact ? 12 : 20, gap: 12 }}
    >
      <View style={{ gap: 8, padding: 12, borderRadius: 10, backgroundColor: colors.surface1 }}>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 12 }}>
          <Metric label="工作区累计缓存率" value="—" colors={colors} />
          <Metric label="最近样本缓存率" value={formatCacheRate(totals.rate)} colors={colors} />
          <Metric label="覆盖会话" value={pending ? "读取中…" : totals.covered + " / " + refs.length} colors={colors} />
        </View>
        <Text style={{ color: colors.foregroundMuted, fontSize: 13 }}>
          Paseo 0.17.1 缺少可统一分母的历史累计用量。最近样本取可确认使用 Codex 的会话各自最后上报的一笔输入。
        </Text>
        {totals.rate !== null && (
          <Text style={{ color: colors.foregroundMuted, fontSize: 13 }}>
            缓存读取 {count(totals.cached)} / 总输入 {count(totals.input)} token
          </Text>
        )}
        {!pending && unavailable > 0 && (
          <Text style={{ color: colors.foregroundMuted, fontSize: 13 }}>
            {unavailable} 个会话当前无法读取用量快照。
          </Text>
        )}
        {refs.length > 0 && (
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ disabled: query.isFetching }}
            disabled={query.isFetching}
            onPress={() => void query.refetch()}
            style={{ alignSelf: "flex-start", paddingVertical: 8 }}
          >
            <Text style={{ color: query.isFetching ? colors.foregroundMuted : colors.accent, fontWeight: "600" }}>
              {query.isFetching ? "正在读取…" : "刷新用量"}
            </Text>
          </Pressable>
        )}
      </View>
      {refs.length === 0 && <Text style={{ color: colors.foregroundMuted }}>当前工作区暂无可见会话。</Text>}
      {refs.map((agentRef) => (
        <AgentRow
          key={agentRef.key}
          agentRef={agentRef}
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
