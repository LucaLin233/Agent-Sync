import { useAgents, useRpc, type PluginButtonIconProps } from "@getpaseo/plugin/client";
import { Icon } from "@getpaseo/plugin/client/ui";
import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { scopeQueryKey, workspaceScopeRpc, type WorkspaceScope } from "../shared/scope";
import type { CumulativeHub } from "./cumulative-hub";
import { useSharedRevision, useSharedScope, useSharedScopeStatus, type SharedStore } from "./shared-store";
import { cumulativeReadEnabled, useCumulativeUsage } from "./use-cumulative";

/**
 * The composer pill's icon is also its reader.
 *
 * A button icon renders inside the host's plugin providers, so its hooks reach
 * the same host-scoped RPC and the same per-installation query cache the
 * popover uses. Reading cumulative usage here through the very key the panel
 * uses means the label appears on mount without opening the panel and without
 * any runtime timer, and opening the panel then observes that reading instead
 * of requesting again.
 */
export function createPillIcon(
  hub: CumulativeHub,
  shared: SharedStore,
  runtime: { adoptScope(scope: WorkspaceScope): boolean },
) {
  return function PillIcon({ workspaceId, host, size, color }: PluginButtonIconProps) {
    const readScope = useRpc(workspaceScopeRpc);
    const runtimeScope = useSharedScope(shared);
    const scopeStatus = useSharedScopeStatus(shared);
    const revision = useSharedRevision(shared);
    // The surface reads a scope itself only while the runtime has not resolved
    // one. Both paths gate the cumulative read on the same settings.
    const ownScope = useQuery({
      queryKey: ["workspace-metrics-scope", host.id],
      queryFn: () => readScope({}),
      enabled: runtimeScope === null && scopeStatus === "pending",
      retry: 2,
      staleTime: 15_000,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
    });
    const scope: WorkspaceScope | null = runtimeScope ?? ownScope.data ?? null;
    // Hand a surface-read scope to the runtime so its label policy can answer
    // "closed" or "out of allowlist" instead of staying on the loading state.
    useEffect(() => {
      if (!ownScope.data || runtimeScope !== null) return;
      runtime.adoptScope(ownScope.data);
    }, [ownScope.data, runtimeScope, runtime]);
    // A scope that cannot be read is a real reason to leave "…"; it must not
    // wait for a cumulative read that will never start.
    useEffect(() => {
      if (!ownScope.isError || runtimeScope !== null || hub.read(workspaceId)) return;
      hub.publish(workspaceId, hub.begin(workspaceId), { rate: null, error: "累计范围读取失败" });
    }, [hub, ownScope.isError, runtimeScope, workspaceId]);
    const agents = useAgents({
      hosts: [host.id],
      where: (agent) => agent.workspaceId === workspaceId && !agent.background,
    });
    // While mounted, this surface owns the read: the runtime turns its own
    // re-read demands into shared revision bumps instead of parallel requests.
    // It lets go on unmount, and the runtime's own routine takes over again.
    useEffect(() => shared.claimSurface(workspaceId), [shared, workspaceId]);
    useCumulativeUsage(
      host.id,
      workspaceId,
      agents,
      cumulativeReadEnabled(scope, workspaceId),
      scopeQueryKey(scope),
      revision,
      hub,
      shared.refreshIntent(revision),
    );
    return <Icon name="Activity" size={size} color={color} />;
  };
}
