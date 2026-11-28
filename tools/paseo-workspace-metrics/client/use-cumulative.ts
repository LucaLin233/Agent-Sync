import { useRpc, type AgentRef } from "@getpaseo/plugin/client";
import { useQuery } from "@tanstack/react-query";
import { cumulativeUsageRpc, type CumulativeUsage } from "../shared/cumulative.ts";
import { workspaceInScope, type WorkspaceScope } from "../shared/scope.ts";
import type { CumulativeHub } from "./cumulative-hub.ts";

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
  refreshRevision: number,
) {
  return [
    "workspace-metrics-cumulative",
    hostId,
    workspaceId,
    [...agentIds].sort(),
    scopeKey,
    refreshRevision,
  ] as const;
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
 * The cumulative read both surfaces share. `refreshRevision` is the shared
 * store's revision: both surfaces pass the same number, so they agree on the
 * key, and a bump moves both to one new request.
 */
export function useCumulativeUsage(
  hostId: string,
  workspaceId: string,
  agents: readonly AgentRef[],
  enabled: boolean,
  scopeKey: string,
  refreshRevision: number,
  hub: CumulativeHub,
  /** A manual or terminal refresh additionally bypasses the server's cache. */
  bypassCache = false,
) {
  const run = useRpc(cumulativeUsageRpc);
  const ids = [...agents].map(({ id }) => id).sort();
  return useQuery({
    queryKey: cumulativeQueryKey(hostId, workspaceId, ids, scopeKey, refreshRevision),
    enabled: enabled && ids.length > 0,
    retry: false,
    staleTime: 15_000,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    queryFn: () => readCumulativeIntoHub({
      run,
      hub,
      workspaceId,
      agentIds: ids,
      refresh: bypassCache,
    }),
  });
}
