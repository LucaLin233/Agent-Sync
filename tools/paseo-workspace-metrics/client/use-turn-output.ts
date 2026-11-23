import { useRpc, type AgentRef } from "@getpaseo/plugin/client";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
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
  // Paseo can report completion before Codex has flushed the rollout, so the
  // first read may still return the previous completed turn. A few bounded
  // refetches after each observed turn cover that gap; the timer is cancelled
  // whenever the observation changes or the hook unmounts.
  const [attempts, setAttempts] = useState(0);
  const turnKey = revision ?? "";
  useEffect(() => {
    setAttempts(0);
  }, [turnKey, scopeKey, scopeRevision, refreshRevision]);
  const query = useQuery({
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
    queryFn: () => run({
      workspaceId,
      agentId: agentRef.id,
      refresh: refreshRevision > 0,
    }),
  });
  useEffect(() => {
    if (!enabled || !turnKey || attempts >= 3) return;
    const timer = setTimeout(() => {
      setAttempts((count) => count + 1);
      void query.refetch();
    }, 1_200);
    return () => clearTimeout(timer);
  }, [enabled, turnKey, attempts, query.refetch]);
  return query;
}
