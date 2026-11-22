import { defineRpc } from "@getpaseo/plugin";
import { z } from "zod";

/**
 * Cumulative Codex usage for one visible workspace. The server only returns
 * aggregate counts and coverage; no session paths, IDs, or content cross the RPC.
 */
export const cumulativeUsageRpc = defineRpc({
  name: "workspace-metrics.cumulative",
  input: z.object({
    workspaceId: z.string().min(1).max(128),
    agentIds: z.array(z.string().min(1).max(128)).min(1).max(200),
  }),
  output: z.object({
    workspaceId: z.string(),
    inputTokens: z.number().int().nonnegative(),
    cachedInputTokens: z.number().int().nonnegative(),
    covered: z.number().int().nonnegative(),
    eligible: z.number().int().nonnegative(),
    missing: z.number().int().nonnegative(),
    unavailable: z.number().int().nonnegative(),
    rate: z.number().min(0).max(1).nullable(),
    error: z.string().nullable(),
  }),
});

export type CumulativeUsage = z.infer<typeof cumulativeUsageRpc.output>;
