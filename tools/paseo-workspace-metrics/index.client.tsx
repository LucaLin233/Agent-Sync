import type { PluginButtonRegistration, PluginClientContext } from "@getpaseo/plugin/client";
import { MetricsPanel } from "./client/panel";
import {
  pillTargetFor,
  projectDirectoryAgent,
  workspaceCacheSummaries,
  type DirectoryAgent,
} from "./shared/agents";
import { formatCachePillLabel } from "./shared/metrics";

interface PillState {
  registration: PluginButtonRegistration;
  workspaceId: string;
  label: string;
}

export default function contribute(client: PluginClientContext) {
  const agents = new Map<string, DirectoryAgent>();
  const pills = new Map<string, PillState>();
  const lifetime = new AbortController();

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

  // Reuses live registrations; only a changed workspace or label causes a write.
  const reconcile = () => {
    if (lifetime.signal.aborted) return;
    const summaries = workspaceCacheSummaries(agents.values());
    for (const [agentId, pill] of pills) {
      const agent = agents.get(agentId);
      const target = agent ? pillTargetFor(agent) : null;
      if (!target || target.workspaceId !== pill.workspaceId) removePill(agentId);
    }
    for (const agent of agents.values()) {
      const target = pillTargetFor(agent);
      if (!target) continue;
      const label = formatCachePillLabel(summaries.get(target.workspaceId)?.rate ?? null);
      const existing = pills.get(agent.id);
      if (!existing) {
        addPill(agent, target.workspaceId, label);
      } else if (existing.label !== label) {
        existing.registration.update({ label });
        existing.label = label;
      }
    }
  };

  const upsert = (source: Parameters<typeof projectDirectoryAgent>[0]) => {
    const agent = projectDirectoryAgent(source);
    agents.set(agent.id, agent);
    reconcile();
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
          reconcile();
        },
        update: (message) => {
          if (message.type !== "agent_update") return;
          const update = message.payload;
          if (update.kind === "remove") {
            agents.delete(update.agentId);
            reconcile();
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
    removeAllPills();
    removeSlashCommand();
    removeCommand();
    removePanel();
  };
}
