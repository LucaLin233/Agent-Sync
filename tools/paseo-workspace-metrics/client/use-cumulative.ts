import { useRpc, type AgentRef } from "@getpaseo/plugin/client";
import { useQuery } from "@tanstack/react-query";
import { cumulativeUsageRpc, type CumulativeUsage } from "../shared/cumulative.ts";
import { workspaceInScope, type WorkspaceScope } from "../shared/scope.ts";
import type { CumulativeHub } from "./cumulative-hub.ts";
import type { SharedScopeStatus } from "./shared-store.ts";

/**
 * The key one cumulative read is cached under. The composer pill and the panel
 * derive it from the same host, workspace, visible members, effective settings
 * and manual refresh, so TanStack makes them one observer of one request
 * instead of two reads of the same data.
 */
export function cumulativeQueryKey(
  hostId: string,
  workspaceId: string,
  agentIds: readonly string[],
  scopeKey: string,
  settingsRevision: number,
  workspaceRevision: number,
) {
  return [
    "workspace-metrics-cumulative",
    hostId,
    workspaceId,
    [...agentIds].sort(),
    scopeKey,
    settingsRevision,
    workspaceRevision,
  ] as const;
}

/**
 * Which scope the cumulative read must use. A live shared scope is the
 * runtime's current settings and always wins, so a stale local copy cannot
 * bypass it. A pending or failed shared scope is only a placeholder — the
 * runtime's subscription has no answer yet, or it closed — so a settings event
 * the panel received itself is the better information and must not be hidden
 * behind it. With neither, the read stays gated off.
 */
export function resolveCumulativeScope(
  sharedScope: WorkspaceScope | null,
  status: SharedScopeStatus,
  localScope: WorkspaceScope | null,
): WorkspaceScope | null {
  if (status === "live" && sharedScope !== null) return sharedScope;
  return localScope ?? sharedScope;
}

/**
 * Whether a surface may issue the read at all: settings resolved and open for
 * this workspace. The hook separately needs at least one visible member.
 */
export function cumulativeReadEnabled(
  scope: WorkspaceScope | null,
  workspaceId: string,
): boolean {
  return scope !== null && workspaceInScope(scope, workspaceId);
}

/**
 * One cumulative read, published into the client's hub so whichever surface
 * issues it moves the composer label. Every reply lands there — a rate, a real
 * zero, or no valid snapshot — and a failure lands too, so the label leaves
 * "…" for its real reason instead of waiting for another surface to answer.
 */
export async function readCumulativeIntoHub(input: {
  run(request: { workspaceId: string; agentIds: string[]; refresh?: boolean }): Promise<CumulativeUsage>;
  hub: CumulativeHub;
  workspaceId: string;
  agentIds: readonly string[];
  refresh: boolean;
}): Promise<CumulativeUsage> {
  const { hub, workspaceId } = input;
  const ticket = hub.begin(workspaceId);
  try {
    const result = await input.run({
      workspaceId,
      agentIds: [...input.agentIds],
      refresh: input.refresh,
    });
    hub.publish(workspaceId, ticket, { rate: result.rate, error: result.error });
    return result;
  } catch (error) {
    hub.publish(workspaceId, ticket, { rate: null, error: "累计用量读取失败" });
    throw error;
  }
}

/**
 * How long an unsuccessful read of one workspace waits before trying again.
 * A mount can race a still-settling connection: the first cumulative RPC is
 * rejected, no member or settings change comes, and nothing else would ever
 * re-issue it. Retrying only in the error state keeps a healthy label quiet and
 * stops the moment a read succeeds.
 */
export const CUMULATIVE_ERROR_RETRY_MS = 15_000;

/** Retry schedule of one cumulative query: only after a failed read. */
export function cumulativeRefetchInterval(
  enabled: boolean,
  status: "pending" | "error" | "success",
): number | false {
  return enabled && status === "error" ? CUMULATIVE_ERROR_RETRY_MS : false;
}

export interface CumulativeQueryInput {
  hostId: string;
  workspaceId: string;
  agentIds: readonly string[];
  enabled: boolean;
  scopeKey: string;
  settingsRevision: number;
  workspaceRevision: number;
  hub: CumulativeHub;
  run(request: { workspaceId: string; agentIds: string[]; refresh?: boolean }): Promise<CumulativeUsage>;
  /** A manual or terminal refresh additionally bypasses the server's cache. */
  bypassCache?: boolean;
}

/**
 * The query both surfaces run. Kept as plain options so the exact object the
 * hooks use can be driven by a real TanStack `QueryObserver` in tests.
 */
export function cumulativeQueryOptions(input: CumulativeQueryInput) {
  const ids = [...input.agentIds].sort();
  const enabled = input.enabled && ids.length > 0;
  return {
    queryKey: cumulativeQueryKey(
      input.hostId,
      input.workspaceId,
      ids,
      input.scopeKey,
      input.settingsRevision,
      input.workspaceRevision,
    ),
    enabled,
    retry: false,
    // Disabled and out-of-allowlist workspaces never reach here (`enabled`
    // false); a failed read of a permitted workspace retries itself.
    refetchInterval: (query: { state: { status: "pending" | "error" | "success" } }) =>
      cumulativeRefetchInterval(enabled, query.state.status),
    staleTime: 15_000,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    queryFn: () => readCumulativeIntoHub({
      run: input.run,
      hub: input.hub,
      workspaceId: input.workspaceId,
      agentIds: ids,
      refresh: input.bypassCache ?? false,
    }),
  };
}

/**
 * The cumulative read both surfaces share. Both revision numbers come from the
 * shared store: the settings generation, and this one workspace's refresh
 * revision. Both surfaces pass the same pair, so they agree on the key; a
 * refresh or finished turn in this workspace moves only this workspace.
 */
export function useCumulativeUsage(
  hostId: string,
  workspaceId: string,
  agents: readonly AgentRef[],
  enabled: boolean,
  scopeKey: string,
  settingsRevision: number,
  workspaceRevision: number,
  hub: CumulativeHub,
  /** A manual or terminal refresh additionally bypasses the server's cache. */
  bypassCache = false,
) {
  const run = useRpc(cumulativeUsageRpc);
  return useQuery(cumulativeQueryOptions({
    hostId,
    workspaceId,
    agentIds: [...agents].map(({ id }) => id),
    enabled,
    scopeKey,
    settingsRevision,
    workspaceRevision,
    hub,
    run,
    bypassCache,
  }));
}
