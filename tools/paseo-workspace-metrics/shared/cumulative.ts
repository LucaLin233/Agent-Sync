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
    /** Manual refresh bypasses the short aggregation cache. */
    refresh: z.boolean().optional(),
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

/**
 * One completed turn's output count for a Codex-backed agent, taken from the
 * same rollout the cumulative reader is allowed to touch. Only a same-turn
 * cumulative output delta is returned; no paths, IDs, or message text cross
 * the RPC.
 */
export const turnOutputRpc = defineRpc({
  name: "workspace-metrics.turn-output",
  input: z.object({
    workspaceId: z.string().min(1).max(128),
    agentId: z.string().min(1).max(128),
    refresh: z.boolean().optional(),
  }),
  output: z.object({
    outputTokens: z.number().int().nonnegative().nullable(),
    /** From the rollout's own task_started -> task_complete timestamps. */
    elapsedMs: z.number().int().nonnegative().nullable(),
    /** Codex's reported time_to_first_token_ms; not the Paseo first-text time. */
    firstTokenMs: z.number().int().nonnegative().nullable(),
    reason: z.enum(["not-codex", "scope", "missing-samples", "read-failed"]).nullable(),
  }),
});

export type TurnOutput = z.infer<typeof turnOutputRpc.output>;
