import type { JsonValue } from "@getpaseo/protocol/agent-types";
import { distinctWorkspaceTitle, fallbackTaskTitle } from "../shared/title.ts";

/**
 * Paseo metadata key holding the exact Chinese title this plugin seeded at
 * creation. It lets the plugin distinguish its own provisional title from a
 * user's manual rename after the async native auto-name has run.
 */
export const WORKSPACE_SEED_METADATA_KEY = "chinese-titles.seeded-title";

export type WorkspaceMetadata = Record<string, JsonValue>;

export interface WorkspaceSeedPlan {
  title: string;
  metadata: WorkspaceMetadata;
}

/**
 * Decides whether workspace.create.before may replace Paseo's first-prompt
 * title. The app's New Workspace request sends firstAgentContext without a
 * title, so a non-empty request title is an explicit user choice and is never
 * replaced. Paseo v0.17.3's native auto-name writes only when the title is
 * empty or exactly that prompt title; the seeded title is different, so the
 * asynchronous English summary cannot overwrite the Chinese one.
 */
export function planWorkspaceTitleSeed(input: {
  title?: string | null;
  prompt?: string | null;
  metadata?: WorkspaceMetadata | null;
  maxChars: number;
}): WorkspaceSeedPlan | null {
  const prompt = input.prompt?.trim();
  if (!prompt) return null;
  if (input.title?.trim()) return null;
  if (input.metadata?.[WORKSPACE_SEED_METADATA_KEY]) return null;
  const fallback = fallbackTaskTitle({ prompt, maxChars: input.maxChars });
  const title = distinctWorkspaceTitle(fallback, prompt, input.maxChars);
  return {
    title,
    metadata: { ...(input.metadata ?? {}), [WORKSPACE_SEED_METADATA_KEY]: title },
  };
}

/** Returns the title this plugin seeded, or null for an unseeded workspace. */
export function seededWorkspaceTitle(
  metadata: Readonly<Record<string, JsonValue>> | null | undefined,
): string | null {
  const value = metadata?.[WORKSPACE_SEED_METADATA_KEY];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}
