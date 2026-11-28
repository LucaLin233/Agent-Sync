import { useRpc, type AgentRef } from "@getpaseo/plugin/client";
import { useQuery } from "@tanstack/react-query";
import { cumulativeUsageRpc, type CumulativeUsage } from "../shared/cumulative";
import { useCumulativeHub } from "./cumulative-hub-context";

/**
 * One cumulative read for the panel. Its result is published into the shared hub
 * before the query resolves, so the composer pill shows it as soon as the panel
 * has a valid reading — no second request needed.
 */
export function useCumulativeUsage(
  workspaceId: string,
  agents: readonly AgentRef[],
  enabled: boolean,
  scopeKey: string,
  scopeRevision: number,
  refreshRevision: number,
) {
  const run = useRpc(cumulativeUsageRpc);
  const hub = useCumulativeHub();
  const ids = [...agents].map(({ id }) => id).sort();
  return useQuery({
    queryKey: ["workspace-metrics-cumulative", workspaceId, ids, scopeKey, scopeRevision, refreshRevision],
    enabled: enabled && ids.length > 0,
    retry: false,
    staleTime: 15_000,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    queryFn: async (): Promise<CumulativeUsage> => {
      const ticket = hub.begin(workspaceId);
      const result = await run({ workspaceId, agentIds: ids, refresh: refreshRevision > 0 });
      // A successful panel read feeds the shared slot the composer pill shows.
      hub.publish(workspaceId, ticket, { rate: result.rate, error: result.error });
      return result;
    },
  });
}
