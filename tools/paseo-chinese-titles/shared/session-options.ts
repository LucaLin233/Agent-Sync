/**
 * Pure rules for the sessions a user may pick in the workspace panel.
 *
 * The panel must never silently fall back to "the first" or "the most recent"
 * session of a workspace: the user picks the conversation that the manual
 * title should summarise. A single eligible session is the only implicit
 * choice, because there is nothing to disambiguate.
 */

export const CHINESE_TITLES_HELPER_LABEL = "paseo-chinese-titles.helper";
export const BETTER_PASEO_HELPER_LABEL = "better-paseo.purpose";
export const BETTER_PASEO_HELPER_PURPOSE = "title-generation";

export interface SessionLike {
  id: string;
  workspaceId?: string | null;
  title?: string | null;
  background?: boolean;
  internal?: boolean;
  archivedAt?: string | null;
  parentAgentId?: string | null;
  labels?: Readonly<Record<string, string>>;
  metadata?: Readonly<Record<string, unknown>>;
  lastActivityAt?: string | null;
  createdAt?: string | null;
}

export interface SelectableSession {
  id: string;
  title: string | null;
  lastActivityAt: string | null;
}

/** Background helpers, sub-agents and this plugin's own naming helper are not user tasks. */
export function isSelectableSession(agent: SessionLike): boolean {
  if (!agent.id) return false;
  if (agent.background === true) return false;
  if (agent.internal === true) return false;
  if (agent.archivedAt) return false;
  if (agent.parentAgentId) return false;
  const labels = agent.labels ?? {};
  if (labels["paseo.parent-agent-id"]) return false;
  if (labels[CHINESE_TITLES_HELPER_LABEL] === "1") return false;
  if (agent.metadata?.[CHINESE_TITLES_HELPER_LABEL] === "1") return false;
  if (labels[BETTER_PASEO_HELPER_LABEL] === BETTER_PASEO_HELPER_PURPOSE) return false;
  return true;
}

function timeOf(value: string | null | undefined): number {
  const parsed = Date.parse(value ?? "");
  return Number.isFinite(parsed) ? parsed : 0;
}

/** Eligible sessions of one workspace, most recently active first, for display only. */
export function selectableSessionsFor(
  agents: readonly SessionLike[],
  workspaceId: string,
): SelectableSession[] {
  return agents
    .filter((agent) => agent.workspaceId === workspaceId && isSelectableSession(agent))
    .sort((left, right) => {
      const activity = timeOf(right.lastActivityAt) - timeOf(left.lastActivityAt);
      if (activity !== 0) return activity;
      const created = timeOf(right.createdAt) - timeOf(left.createdAt);
      if (created !== 0) return created;
      return left.id.localeCompare(right.id);
    })
    .map((agent) => ({
      id: agent.id,
      title: agent.title?.trim() || null,
      lastActivityAt: agent.lastActivityAt ?? null,
    }));
}

/**
 * Keeps an explicit selection only while it is still eligible. With exactly one
 * eligible session that session is preselected; with several, nothing is.
 */
export function resolveSessionSelection(
  sessions: readonly SelectableSession[],
  selectedId: string | null | undefined,
): string | null {
  if (selectedId && sessions.some((session) => session.id === selectedId)) return selectedId;
  return sessions.length === 1 ? sessions[0].id : null;
}
