export interface GenerationPlan {
  workspace: boolean;
  agent: "none" | "reuse-workspace" | "generate";
}

/**
 * Session-only must call generateTitle once. A shared first task reuses the
 * workspace result only when the same agent won; a competing session gets its
 * own single session generation after the workspace winner was chosen.
 */
export function planTitleGeneration(input: {
  workspaceEligible: boolean;
  agentEligible: boolean;
  winnerIsAgent: boolean;
}): GenerationPlan {
  if (!input.workspaceEligible) {
    return { workspace: false, agent: input.agentEligible ? "generate" : "none" };
  }
  if (!input.agentEligible) return { workspace: true, agent: "none" };
  return { workspace: true, agent: input.winnerIsAgent ? "reuse-workspace" : "generate" };
}
