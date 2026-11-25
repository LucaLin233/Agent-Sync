import type { PluginClientContext } from "@getpaseo/plugin/client";
import { Platform } from "react-native";
import { MetricsPanel, MetricsSheet } from "./client/panel";
import { startPillRuntime } from "./client/pill-runtime";
import { WorkspaceMetricsSettings } from "./client/settings";
import { cumulativeUsageRpc } from "./shared/cumulative";
import { workspaceSettingsSubscription } from "./shared/scope";

export default function contribute(client: PluginClientContext) {
  const native = Platform.OS === "ios" || Platform.OS === "android";
  const runtime = startPillRuntime({
    addPill({ workspaceId, agentId, title, label, onPress }) {
      return client.addComposerPill({
        id: "open-metrics",
        workspaceId,
        agentId,
        button: {
          title,
          icon: "Activity",
          label,
          behavior: native
            ? { kind: "popover", Content: MetricsSheet }
            : { kind: "action", onPress },
        },
      });
    },
    openPanel(workspaceId, agentId) {
      client.openPanel("metrics", { workspaceId, agentId });
    },
    requestCumulative: (input) => client.rpc(cumulativeUsageRpc, input),
    subscribeAgents(handlers) {
      const lifetime = new AbortController();
      void client.paseo.agents
        .list({ subscribe: {}, signal: lifetime.signal })
        .then(({ subscription }) => {
          subscription.subscribe({
            snapshot: ({ entries }) => {
              handlers.snapshot(entries.map(({ agent }) => agent));
            },
            update: (message) => {
              if (message.type !== "agent_update") return;
              handlers.update(message);
            },
          });
          return undefined;
        })
        .catch((error) => {
          if (!lifetime.signal.aborted) console.error("Agent observation failed", error);
        });
      return () => lifetime.abort();
    },
    subscribeSettings({ next, closed }) {
      return client.subscribe(workspaceSettingsSubscription, {}, (event) => next(event), {
        onClosed: closed,
      });
    },
  });

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

  return () => {
    runtime.dispose();
    removeSettings();
    removeSlashCommand();
    removeCommand();
    removePanel();
  };
}
