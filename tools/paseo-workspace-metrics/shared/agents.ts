/** Public directory fields needed to place a composer pill. */
export interface AgentDirectoryEntry {
  id: string;
  workspaceId?: string | null;
  archivedAt?: string | null;
  background?: boolean;
  /** Public status only: used to notice a turn reaching its terminal state. */
  status?: string | null;
  /** Public timestamp only: a terminal refresh after the last observed turn. */
  updatedAt?: string | null;
}

export interface DirectoryAgent {
  id: string;
  workspaceId: string | null;
  archived: boolean;
  background: boolean;
  status: string | null;
  updatedAt: string | null;
}

export interface PillTarget {
  id: string;
  workspaceId: string;
}

export function projectDirectoryAgent(agent: AgentDirectoryEntry): DirectoryAgent {
  const archived = Boolean(agent.archivedAt);
  const background = Boolean(agent.background);
  return {
    id: agent.id,
    workspaceId: agent.workspaceId ?? null,
    archived,
    background,
    status: agent.status ?? null,
    updatedAt: agent.updatedAt ?? null,
  };
}

/** Archived, background, and detached agents cannot own a composer pill. */
export function pillTarget(agent: AgentDirectoryEntry): PillTarget | null {
  if (!agent.workspaceId || agent.archivedAt || agent.background) return null;
  return { id: agent.id, workspaceId: agent.workspaceId };
}

export function pillTargetFor(agent: DirectoryAgent): PillTarget | null {
  if (!agent.workspaceId || agent.archived || agent.background) return null;
  return { id: agent.id, workspaceId: agent.workspaceId };
}
