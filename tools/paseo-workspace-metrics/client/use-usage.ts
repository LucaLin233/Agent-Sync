import { usePaseo, type AgentRef } from "@getpaseo/plugin/client";
import { useQuery } from "@tanstack/react-query";
import { latestCacheSample, type ReportedUsage } from "../shared/metrics";

export interface UsageSnapshot {
  cacheSample: ReturnType<typeof latestCacheSample>;
  usage: ReportedUsage | null;
}

export function useWorkspaceUsage(
  hostId: string,
  workspaceId: string,
  agents: readonly AgentRef[],
) {
  const paseo = usePaseo();
  const refs = [...agents].sort((left, right) => left.id.localeCompare(right.id));
  return useQuery({
    queryKey: ["workspace-metrics", hostId, workspaceId, refs.map(({ id }) => id)],
    enabled: refs.length > 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    retry: false,
    queryFn: async ({ signal }) => {
      const snapshots = new Map<string, UsageSnapshot>();
      // A large workspace should not start all exact-ID requests at once.
      const batchSize = 6;
      for (let offset = 0; offset < refs.length && !signal.aborted; offset += batchSize) {
        const batch = refs.slice(offset, offset + batchSize);
        // Failed or missing reads stay absent and cannot become zero-token samples.
        await Promise.allSettled(batch.map(async (agentRef) => {
          const handle = paseo.agents.ref(agentRef);
          const result = await handle.refresh();
          if (!result || handle.workspaceId !== workspaceId || handle.archivedAt) return;
          const reported = handle.lastUsage;
          const usage = reported && {
            inputTokens: reported.inputTokens,
            cachedInputTokens: reported.cachedInputTokens,
            outputTokens: reported.outputTokens,
            contextWindowUsedTokens: reported.contextWindowUsedTokens,
            contextWindowMaxTokens: reported.contextWindowMaxTokens,
          };
          // Custom providers rewrite the outer provider ID. Codex retains its adapter marker here.
          const cacheSample = latestCacheSample(
            result.agent.provider,
            usage,
            result.agent.persistence?.metadata?.provider,
          );
          snapshots.set(agentRef.id, { usage, cacheSample });
        }));
      }
      return snapshots;
    },
  });
}
