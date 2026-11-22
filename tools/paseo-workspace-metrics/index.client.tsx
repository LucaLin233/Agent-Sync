import type { PluginButtonRegistration, PluginClientContext } from "@getpaseo/plugin/client";
import { MetricsPanel } from "./client/panel";
import { WorkspaceMetricsSettings } from "./client/settings";
import { pillTargetFor, projectDirectoryAgent, workspaceCacheSummaries, type DirectoryAgent } from "./shared/agents";
import { cumulativeUsageRpc } from "./shared/cumulative";
import { formatCachePillLabel, formatRecentPillLabel } from "./shared/metrics";
import { workspaceSettingsSubscription } from "./shared/scope";

interface PillState {
  registration: PluginButtonRegistration;
  workspaceId: string;
  label: string;
}

interface CumulativeState {
  rate: number | null;
  error: string | null;
}

const CUMULATIVE_MIN_INTERVAL_MS = 10_000;

export default function contribute(client: PluginClientContext) {
  const agents = new Map<string, DirectoryAgent>();
  const pills = new Map<string, PillState>();
  const cumulative = new Map<string, CumulativeState>();
  let scope: { ids: Set<string>; allWorkspaces: boolean; enabled: boolean; error: string | null } | null = null;
  const timers = new Map<string, ReturnType<typeof setTimeout>>();
  const lastRequest = new Map<string, number>();
  const lifetime = new AbortController();
  let generation = 0;

  const removePill = (agentId: string) => {
    pills.get(agentId)?.registration.remove();
    pills.delete(agentId);
  };

  const addPill = (agent: DirectoryAgent, workspaceId: string, label: string) => {
    const registration = client.addComposerPill({
      id: "open-metrics",
      workspaceId,
      agentId: agent.id,
      button: {
        title: "打开工作区用量",
        icon: "Activity",
        label,
        behavior: {
          kind: "action",
          onPress() {
            client.openPanel("metrics", { workspaceId, agentId: agent.id });
          },
        },
      },
    });
    pills.set(agent.id, { registration, workspaceId, label });
  };

  const agentIdsFor = (workspaceId: string) => {
    const ids: string[] = [];
    for (const agent of agents.values()) {
      if (agent.workspaceId === workspaceId && !agent.archived && !agent.background) ids.push(agent.id);
    }
    return ids.sort();
  };

  const labelFor = (workspaceId: string, recent: ReturnType<typeof workspaceCacheSummaries>) => {
    const recentLabel = () => formatRecentPillLabel(recent.get(workspaceId)?.rate);
    if (!scope) return "累计 …";
    if (!scope.enabled || !(scope.allWorkspaces || scope.ids.has(workspaceId))) return recentLabel();
    const state = cumulative.get(workspaceId);
    if (!state) return "缓存 …";
    if (state.error) return recentLabel();
    return formatCachePillLabel(state.rate);
  };

  // Reuses live registrations; only a changed workspace or label causes a write.
  const reconcile = () => {
    if (lifetime.signal.aborted) return;
    const recent = workspaceCacheSummaries(agents.values());
    for (const [agentId, pill] of pills) {
      const agent = agents.get(agentId);
      const target = agent ? pillTargetFor(agent) : null;
      if (!target || target.workspaceId !== pill.workspaceId) removePill(agentId);
    }
    for (const agent of agents.values()) {
      const target = pillTargetFor(agent);
      if (!target) continue;
      const label = labelFor(target.workspaceId, recent);
      const existing = pills.get(agent.id);
      if (!existing) {
        addPill(agent, target.workspaceId, label);
      } else if (existing.label !== label) {
        existing.registration.update({ label });
        existing.label = label;
      }
    }
  };

  // Only workspaces in the effective scope are requested; the server revalidates each exact agent.
  const scheduleCumulative = (only?: ReadonlySet<string>) => {
    if (!scope || lifetime.signal.aborted) return;
    if (!scope.enabled) {
      for (const timer of timers.values()) clearTimeout(timer);
      timers.clear();
      cumulative.clear();
      return;
    }
    const workspaces = new Set<string>();
    for (const agent of agents.values()) {
      if (!agent.workspaceId || agent.archived || agent.background) continue;
      if (scope.allWorkspaces || scope.ids.has(agent.workspaceId)) {
        workspaces.add(agent.workspaceId);
      }
    }
    for (const workspaceId of workspaces) {
      if (only && !only.has(workspaceId)) continue;
      if (timers.has(workspaceId)) continue;
      const wait = Math.max(0, CUMULATIVE_MIN_INTERVAL_MS - (Date.now() - (lastRequest.get(workspaceId) ?? 0)));
      const timer = setTimeout(() => {
        timers.delete(workspaceId);
        if (lifetime.signal.aborted) return;
        const agentIds = agentIdsFor(workspaceId);
        if (agentIds.length === 0) {
          cumulative.delete(workspaceId);
          reconcile();
          return;
        }
        lastRequest.set(workspaceId, Date.now());
        const requestGeneration = generation;
        void client.rpc(cumulativeUsageRpc, { workspaceId, agentIds })
          .then((result) => {
            if (lifetime.signal.aborted || generation !== requestGeneration) return;
            cumulative.set(workspaceId, { rate: result.rate, error: result.error });
            reconcile();
          })
          .catch((error) => {
            if (lifetime.signal.aborted || generation !== requestGeneration) return;
            cumulative.set(workspaceId, { rate: null, error: "累计用量读取失败" });
            console.error("Cumulative usage failed", error);
            reconcile();
          });
      }, wait);
      timers.set(workspaceId, timer);
    }
    for (const [workspaceId, timer] of timers) {
      if (workspaces.has(workspaceId)) continue;
      clearTimeout(timer);
      timers.delete(workspaceId);
      cumulative.delete(workspaceId);
    }
  };

  // An increment only refreshes the workspace it touched; a full snapshot refreshes all.
  const applyAgentChange = (affected?: ReadonlySet<string>) => {
    reconcile();
    scheduleCumulative(affected);
  };

  const upsert = (source: Parameters<typeof projectDirectoryAgent>[0]) => {
    const previous = agents.get(source.id);
    const agent = projectDirectoryAgent(source);
    agents.set(agent.id, agent);
    const affected = new Set<string>();
    if (previous?.workspaceId) affected.add(previous.workspaceId);
    if (agent.workspaceId) affected.add(agent.workspaceId);
    applyAgentChange(affected);
  };

  const removeAllPills = () => {
    for (const pill of pills.values()) pill.registration.remove();
    pills.clear();
  };

  const removePanel = client.addWorkspacePanel({
    id: "metrics",
    title: "工作区用量",
    icon: "Activity",
    Component: MetricsPanel,
  });
  const removeSettings = client.addSettingsScreen({
    id: "workspace-metrics",
    title: "工作区用量",
    icon: "Settings",
    Component: WorkspaceMetricsSettings,
  });
  const removeCommand = client.addCommandCenterItem({
    id: "open-metrics",
    title: "打开工作区用量",
    icon: "Activity",
    context: "workspace",
    keywords: ["cache", "tokens", "metrics", "缓存", "会话"],
    onSelect({ openPanel }) {
      openPanel("metrics");
    },
  });
  const removeSlashCommand = client.addSlashCommand({
    name: "metrics",
    description: "打开当前工作区用量面板",
    argumentHint: "",
    context: "workspace",
    onSubmit({ openPanel }) {
      openPanel("metrics");
    },
  });

  // Settings changes clear every cached value and refresh all pills without a reload.
  const settingsSubscription = client.subscribe(workspaceSettingsSubscription, {}, (event) => {
    if (lifetime.signal.aborted) return;
    generation += 1;
    scope = {
      ids: new Set(event.workspaceIds),
      allWorkspaces: event.allWorkspaces,
      enabled: event.enabled,
      error: event.error,
    };
    cumulative.clear();
    lastRequest.clear();
    for (const timer of timers.values()) clearTimeout(timer);
    timers.clear();
    reconcile();
    scheduleCumulative();
  }, {
    onClosed() {
      if (lifetime.signal.aborted) return;
      generation += 1;
      scope = { ids: new Set(), allWorkspaces: false, enabled: false, error: "设置订阅已关闭" };
      cumulative.clear();
      reconcile();
      scheduleCumulative();
    },
  });

  // This client's own daemon. A fresh snapshot after reconnection reconciles every pill.
  void client.paseo.agents
    .list({ subscribe: {}, signal: lifetime.signal })
    .then(({ subscription }) => {
      subscription.subscribe({
        snapshot: ({ entries }) => {
          agents.clear();
          for (const { agent } of entries) {
            const projected = projectDirectoryAgent(agent);
            agents.set(projected.id, projected);
          }
          applyAgentChange();
        },
        update: (message) => {
          if (message.type !== "agent_update") return;
          const update = message.payload;
          if (update.kind === "remove") {
            const previous = agents.get(update.agentId);
            agents.delete(update.agentId);
            applyAgentChange(new Set(previous?.workspaceId ? [previous.workspaceId] : []));
          } else {
            upsert(update.agent);
          }
        },
      });
      return undefined;
    })
    .catch((error) => {
      if (!lifetime.signal.aborted) console.error("Agent observation failed", error);
    });

  return () => {
    lifetime.abort();
    for (const timer of timers.values()) clearTimeout(timer);
    timers.clear();
    removeAllPills();
    settingsSubscription();
    removeSettings();
    removeSlashCommand();
    removeCommand();
    removePanel();
  };
}
