import { defineRpc, defineSubscription } from "@getpaseo/plugin";
import { z } from "zod";

const workspaceIdSchema = z.string().min(1).max(128);

/** The effective scope shared by the RPC, the live subscription, the panel, and the pill. */
export const workspaceScopeOutput = z.object({
  enabled: z.boolean(),
  workspaceIds: z.array(workspaceIdSchema),
  allWorkspaces: z.boolean(),
  codexHomeConfigured: z.boolean(),
  error: z.string().nullable(),
});

/** The daemon-local allowlist. It never returns filesystem paths. */
export const workspaceScopeRpc = defineRpc({
  name: "workspace-metrics.scope",
  input: z.object({}),
  output: workspaceScopeOutput,
});

/**
 * Pushes the effective scope whenever the host settings change. `attempt` only
 * changes the subscription identity, so a client can reopen it after the host
 * dropped or rejected it; the handler ignores the value.
 */
export const workspaceSettingsSubscription = defineSubscription({
  name: "workspace-metrics.settings",
  input: z.object({ attempt: z.number().int().nonnegative().optional() }),
  event: workspaceScopeOutput,
});

export type WorkspaceScope = z.infer<typeof workspaceScopeOutput>;

export interface WorkspaceSettingsValues {
  cumulativeEnabled?: boolean;
  allWorkspaces?: boolean;
  workspaceIds?: readonly string[];
}

export interface EffectiveWorkspaceScope {
  enabled: boolean;
  allWorkspaces: boolean;
  workspaceIds: string[];
  error: string | null;
}

function normalizeIds(values: readonly string[] | undefined): string[] {
  return [...new Set((values ?? []).filter((id) => workspaceIdSchema.safeParse(id).success))];
}

/**
 * One canonical reading of host settings. `cumulativeEnabled` is the explicit switch;
 * older saved documents fall back to the previous shape, where an allowlist or
 * `allWorkspaces: true` meant the feature was on.
 */
export function effectiveWorkspaceScope(values: WorkspaceSettingsValues = {}): EffectiveWorkspaceScope {
  const ids = normalizeIds(values.workspaceIds);
  const legacyEnabled = values.allWorkspaces === true || ids.length > 0;
  const enabled = values.cumulativeEnabled ?? legacyEnabled;
  if (!enabled) return { enabled: false, allWorkspaces: false, workspaceIds: [], error: null };
  if (values.allWorkspaces === true || (values.allWorkspaces !== false && ids.length === 0)) {
    return { enabled: true, allWorkspaces: true, workspaceIds: [], error: null };
  }
  if (ids.length === 0) {
    return { enabled: true, allWorkspaces: false, workspaceIds: [], error: "至少填写一个 workspace ID" };
  }
  return { enabled: true, allWorkspaces: false, workspaceIds: ids, error: null };
}

/** One policy shared by the panel, the composer pill, and the server check. */
export function workspaceInScope(scope: WorkspaceScope, workspaceId: string): boolean {
  return scope.enabled && (scope.allWorkspaces || scope.workspaceIds.includes(workspaceId));
}
