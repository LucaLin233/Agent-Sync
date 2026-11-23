import { useRpc, type AgentRef } from "@getpaseo/plugin/client";
import { useQuery } from "@tanstack/react-query";
import { turnOutputRpc } from "../shared/cumulative";

/**
 * The most recent completed Codex turn, measured only from that session's own
 * rollout: native task_started/task_complete boundaries plus the cumulative
 * output counter. `revision` is a refresh trigger (the latest observed Paseo
 * turn id), never a time window used for slicing.
 */
export function useTurnOutput(
  agentRef: AgentRef,
  workspaceId: string,
  enabled: boolean,
  scopeKey: string,
  scopeRevision: number,
  refreshRevision: number,
  revision: string | null,
) {
  const run = useRpc(turnOutputRpc);
  return useQuery({
    // Workspace, effective settings, and an explicit refresh are part of the
    // key so another workspace, a changed scope, or a manual refresh never
    // reuses an older rollout read.
    queryKey: [
      "workspace-metrics-turn",
      workspaceId,
      agentRef.id,
      scopeKey,
      scopeRevision,
      refreshRevision,
      revision ?? "",
    ],
    enabled,
    retry: false,
    staleTime: 15_000,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    queryFn: () => run({ workspaceId, agentId: agentRef.id }),
  });
}
