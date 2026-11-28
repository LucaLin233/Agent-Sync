import type {
  PluginButtonContentProps,
  PluginClientContext,
  PluginWorkspacePanelProps,
} from "@getpaseo/plugin/client";
import { Platform } from "react-native";
import { MetricsPanel, MetricsSheet } from "./client/panel";
import { createCumulativeHub } from "./client/cumulative-hub";
import { CumulativeHubContext } from "./client/cumulative-hub-context";
import { createPillIcon } from "./client/pill-icon";
import { createSharedStore } from "./client/shared-store";
import { SharedStoreProvider } from "./client/shared-store-context";
import { startPillRuntime } from "./client/pill-runtime";
import { WorkspaceMetricsSettings } from "./client/settings";
import { cumulativeUsageRpc } from "./shared/cumulative";
import { workspaceScopeRpc, workspaceSettingsSubscription, type WorkspaceScope } from "./shared/scope";

export default function contribute(client: PluginClientContext) {
  const native = Platform.OS === "ios" || Platform.OS === "android";
  // One hub per loaded client: the composer pill and every panel of this client
  // publish and read the same cumulative reading.
  const hub = createCumulativeHub();
  // The scope, refresh revision and read ownership the pill runtime and every
  // surface of this client share, so their cumulative queries are one key.
  const shared = createSharedStore();
  const PanelWithHub = (props: PluginWorkspacePanelProps) => (
    <CumulativeHubContext.Provider value={hub}>
      <SharedStoreProvider store={shared}>
        <MetricsPanel {...props} />
      </SharedStoreProvider>
    </CumulativeHubContext.Provider>
  );
  const SheetWithHub = (props: PluginButtonContentProps) => (
    <CumulativeHubContext.Provider value={hub}>
      <SharedStoreProvider store={shared}>
        <MetricsSheet {...props} />
      </SharedStoreProvider>
    </CumulativeHubContext.Provider>
  );
  // The pill icon owns the workspace's shared cumulative query, so the label can
  // appear on mount without opening the panel or waiting for a runtime read. It
  // is created before the runtime that hands it the scope, but only runs once
  // mounted; `surface.runtime` is set right after the runtime exists.
  const surface: { runtime: { adoptScope(scope: WorkspaceScope): boolean } | null } = { runtime: null };
  const PillIcon = createPillIcon(hub, shared, {
    adoptScope: (scope) => surface.runtime?.adoptScope(scope) ?? false,
  });
  const runtime = startPillRuntime({
    addPill({ workspaceId, agentId, title, label, onPress }) {
      return client.addComposerPill({
        id: "open-metrics",
        workspaceId,
        agentId,
        button: {
          title,
          icon: PillIcon,
          label,
          behavior: native
            ? { kind: "popover", Content: SheetWithHub }
            : { kind: "action", onPress },
        },
      });
    },
    openPanel(workspaceId, agentId) {
      client.openPanel("metrics", { workspaceId, agentId });
    },
    requestCumulative: (input) => client.rpc(cumulativeUsageRpc, input),
    requestScope: () => client.rpc(workspaceScopeRpc, {}),
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
  }, hub, shared);
  surface.runtime = runtime;

  const removePanel = client.addWorkspacePanel({
    id: "metrics",
    title: "工作区用量",
    icon: "Activity",
    Component: PanelWithHub,
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
