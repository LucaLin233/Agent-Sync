import { useRpc, type AgentRef } from "@getpaseo/plugin/client";
import { useQuery } from "@tanstack/react-query";
import { cumulativeUsageRpc } from "../shared/cumulative";

export function useCumulativeUsage(
  workspaceId: string,
  agents: readonly AgentRef[],
  enabled: boolean,
  scopeKey: string,
  scopeRevision: number,
) {
  const run = useRpc(cumulativeUsageRpc);
  const ids = [...agents].map(({ id }) => id).sort();
  return useQuery({
    queryKey: ["workspace-metrics-cumulative", workspaceId, ids, scopeKey, scopeRevision],
    enabled: enabled && ids.length > 0,
    retry: false,
    staleTime: 15_000,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    queryFn: () => run({ workspaceId, agentIds: ids }),
  });
}
