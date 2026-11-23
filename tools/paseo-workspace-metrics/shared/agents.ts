import {
  latestCacheSample,
  summarizeLatestSamples,
  type CacheSample,
  type CacheSummary,
  type ReportedUsage,
} from "./metrics.ts";

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

/** Only these directory fields are read; the raw snapshot is never retained. */
export interface DirectoryAgentSource extends AgentDirectoryEntry {
  provider: string;
  lastUsage?: ReportedUsage | null;
  /** The only persistence field read: the non-secret Codex adapter marker. */
  persistence?: { metadata?: { provider?: unknown } | null } | null;
}

export interface DirectoryAgent {
  id: string;
  workspaceId: string | null;
  archived: boolean;
  background: boolean;
  status: string | null;
  updatedAt: string | null;
  /** Computed latest valid sample; raw usage and the source snapshot are dropped. */
  sample: CacheSample | null;
}

export interface PillTarget {
  id: string;
  workspaceId: string;
}

export function projectDirectoryAgent(agent: DirectoryAgentSource): DirectoryAgent {
  const archived = Boolean(agent.archivedAt);
  const background = Boolean(agent.background);
  return {
    id: agent.id,
    workspaceId: agent.workspaceId ?? null,
    archived,
    background,
    status: agent.status ?? null,
    updatedAt: agent.updatedAt ?? null,
    sample: archived || background
      ? null
      : latestCacheSample(agent.provider, agent.lastUsage, agent.persistence?.metadata?.provider),
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

/** One latest sample per visible conversation, summed within each workspace. */
export function workspaceCacheSummaries(
  agents: Iterable<DirectoryAgent>,
): Map<string, CacheSummary> {
  const samples = new Map<string, CacheSample[]>();
  for (const agent of agents) {
    if (!agent.workspaceId || agent.archived || agent.background || agent.sample === null) continue;
    const list = samples.get(agent.workspaceId);
    if (list) list.push(agent.sample);
    else samples.set(agent.workspaceId, [agent.sample]);
  }
  const summaries = new Map<string, CacheSummary>();
  for (const [workspaceId, list] of samples) {
    summaries.set(workspaceId, summarizeLatestSamples(list));
  }
  return summaries;
}
