import type { CumulativeUsage } from "../shared/cumulative.ts";
import { pillTargetFor, projectDirectoryAgent, type AgentDirectoryEntry, type DirectoryAgent } from "../shared/agents.ts";
import {
  formatPillLabel,
  formatPillTitle,
  type PillCacheBasis,
} from "../shared/metrics.ts";
import { workspaceInScope, type WorkspaceScope } from "../shared/scope.ts";

export interface PillHandle {
  update(patch: { title?: string; label?: string }): void;
  remove(): void;
}

export interface PillRuntimeDeps {
  addPill(input: {
    workspaceId: string;
    agentId: string;
    title: string;
    label: string;
    onPress(): void;
  }): PillHandle;
  /** Opens the same workspace panel the pill always opened. */
  openPanel(workspaceId: string, agentId: string): void;
  /** The same cumulative RPC the panel uses; `refresh` bypasses its short caches. */
  requestCumulative(input: { workspaceId: string; agentIds: string[]; refresh?: boolean }): Promise<CumulativeUsage>;
  subscribeAgents(handlers: {
    snapshot(entries: readonly AgentDirectoryEntry[]): void;
    update(message: { type: string; payload: AgentUpdatePayload }): void;
  }): () => void;
  subscribeSettings(values: {
    next(scope: WorkspaceScope): void;
    closed(): void;
  }): () => void;
}

export interface AgentUpdatePayload {
  kind: "upsert" | "remove";
  agentId?: string;
  agent?: AgentDirectoryEntry;
}

interface PillState {
  handle: PillHandle;
  workspaceId: string;
  label: string;
  title: string;
}

interface CumulativeState {
  rate: number | null;
  error: string | null;
}

/** Routine directory-driven reads stay at most one per this window per workspace. */
const CUMULATIVE_MIN_INTERVAL_MS = 10_000;
/** A finished turn may be flushed to its rollout after the directory update. */
const FOLLOW_UP_DELAY_MS = 1_200;
const FOLLOW_UP_LIMIT = 3;
const TERMINAL_STATUSES = new Set(["idle", "error", "closed"]);
/** Waits before reopening a closed settings subscription; the last one repeats. */
const SETTINGS_RETRY_DELAYS_MS = [1_000, 2_000, 5_000, 10_000, 30_000];

const EMPTY_SCOPE: WorkspaceScope = {
  enabled: false,
  workspaceIds: [],
  allWorkspaces: false,
  codexHomeConfigured: false,
  error: "设置订阅已关闭",
};

/**
 * Composer-pill runtime: one pill per visible agent showing the cumulative
 * cache rate from the same RPC the panel shows. Directory events drive the
 * reads; a finished turn additionally gets a small number of bounded re-reads
 * so a rollout flushed after the event still reaches the label.
 */
export function startPillRuntime(deps: PillRuntimeDeps) {
  const agents = new Map<string, DirectoryAgent>();
  const pills = new Map<string, PillState>();
  const cumulative = new Map<string, CumulativeState>();
  const routineTimers = new Map<string, ReturnType<typeof setTimeout>>();
  const followUpTimers = new Map<string, ReturnType<typeof setTimeout>>();
  const followUpsLeft = new Map<string, number>();
  const lastRequest = new Map<string, number>();
  /** Bumped whenever the effective member set of a workspace changes. */
  const memberVersions = new Map<string, number>();
  /** Monotonic per-workspace request id; only the newest may land. */
  const requestSequences = new Map<string, number>();
  const members = new Map<string, string>();
  let scope: WorkspaceScope | null = null;
  let generation = 0;
  let disposed = false;

  const removePill = (agentId: string) => {
    pills.get(agentId)?.handle.remove();
    pills.delete(agentId);
  };

  // The same policy the panel uses, so both surfaces agree on open/closed.
  const inScope = (workspaceId: string) => scope !== null && workspaceInScope(scope, workspaceId);

  const agentIdsFor = (workspaceId: string) => {
    const ids: string[] = [];
    for (const agent of agents.values()) {
      if (agent.workspaceId === workspaceId && !agent.archived && !agent.background) ids.push(agent.id);
    }
    return ids.sort();
  };

  /**
   * The cumulative slot only ever reflects the cumulative RPC. Settings that
   * put this workspace out of scope, a failed read, or a reply without a valid
   * snapshot all leave the slot empty with its own reason.
   */
  const cumulativeSlot = (workspaceId: string): PillCacheBasis => {
    if (!scope) return { kind: "loading" };
    if (scope.error) return { kind: "unavailable", reason: "累计设置错误：" + scope.error };
    if (!scope.enabled) return { kind: "unavailable", reason: "累计统计已关闭" };
    if (!inScope(workspaceId)) return { kind: "unavailable", reason: "不在本机累计名单" };
    const state = cumulative.get(workspaceId);
    if (!state) return { kind: "loading" };
    if (state.error) return { kind: "unavailable", reason: "累计读取失败：" + state.error };
    return { kind: "ready", rate: state.rate };
  };

  const labelFor = (workspaceId: string) => formatPillLabel(cumulativeSlot(workspaceId));

  const titleFor = (workspaceId: string) => formatPillTitle(cumulativeSlot(workspaceId));

  // Reuses live registrations; only a changed workspace, label, or title causes a write.
  const reconcile = () => {
    if (disposed) return;
    for (const [agentId, pill] of pills) {
      const agent = agents.get(agentId);
      const target = agent ? pillTargetFor(agent) : null;
      if (!target || target.workspaceId !== pill.workspaceId) removePill(agentId);
    }
    for (const agent of agents.values()) {
      const target = pillTargetFor(agent);
      if (!target) continue;
      const label = labelFor(target.workspaceId);
      const title = titleFor(target.workspaceId);
      const existing = pills.get(agent.id);
      if (!existing) {
        const handle = deps.addPill({
          workspaceId: target.workspaceId,
          agentId: agent.id,
          title,
          label,
          onPress: () => deps.openPanel(target.workspaceId, agent.id),
        });
        pills.set(agent.id, { handle, workspaceId: target.workspaceId, label, title });
      } else if (existing.label !== label || existing.title !== title) {
        existing.handle.update({ label, title });
        existing.label = label;
        existing.title = title;
      }
    }
  };

  const clearRoutine = (workspaceId?: string) => {
    for (const [key, timer] of routineTimers) {
      if (workspaceId && key !== workspaceId) continue;
      clearTimeout(timer);
      routineTimers.delete(key);
    }
  };

  const clearFollowUps = (workspaceId?: string) => {
    for (const [key, timer] of followUpTimers) {
      if (workspaceId && key !== workspaceId) continue;
      clearTimeout(timer);
      followUpTimers.delete(key);
      followUpsLeft.delete(key);
    }
  };

  const requestCumulative = (workspaceId: string, refresh: boolean) => {
    if (disposed) return;
    const agentIds = agentIdsFor(workspaceId);
    if (agentIds.length === 0) {
      cumulative.delete(workspaceId);
      members.delete(workspaceId);
      reconcile();
      return;
    }
    const seq = (requestSequences.get(workspaceId) ?? 0) + 1;
    requestSequences.set(workspaceId, seq);
    const version = memberVersions.get(workspaceId) ?? 0;
    const requestGeneration = generation;
    lastRequest.set(workspaceId, Date.now());
    // A late reply is dropped when settings moved, members changed, or a newer
    // request exists; success and failure take the same guard.
    const live = () =>
      !disposed &&
      requestGeneration === generation &&
      seq === requestSequences.get(workspaceId) &&
      version === (memberVersions.get(workspaceId) ?? 0);
    void deps
      .requestCumulative({ workspaceId, agentIds, refresh })
      .then((result) => {
        if (!live()) return;
        cumulative.set(workspaceId, { rate: result.rate, error: result.error });
        reconcile();
      })
      .catch(() => {
        if (!live()) return;
        cumulative.set(workspaceId, { rate: null, error: "累计用量读取失败" });
        reconcile();
      });
  };

  // Bounded, non-periodic: only a terminal transition starts this sequence.
  const scheduleFollowUp = (workspaceId: string) => {
    if (disposed) return;
    if (followUpTimers.has(workspaceId)) {
      // Another turn finished while the chain is still running. Keep the one
      // in-flight timer, but restore the budget so the newer turn's rollout
      // still gets a read after it lands. The event count bounds this, not a
      // poll: a chain only continues while real terminal transitions arrive.
      followUpsLeft.set(workspaceId, FOLLOW_UP_LIMIT);
      return;
    }
    followUpsLeft.set(workspaceId, FOLLOW_UP_LIMIT);
    const tick = () => {
      followUpTimers.delete(workspaceId);
      if (disposed) return;
      const left = followUpsLeft.get(workspaceId) ?? 0;
      if (left <= 0) {
        followUpsLeft.delete(workspaceId);
        return;
      }
      followUpsLeft.set(workspaceId, left - 1);
      if (!inScope(workspaceId)) {
        followUpsLeft.delete(workspaceId);
        return;
      }
      requestCumulative(workspaceId, true);
      if (left - 1 > 0) {
        const timer = setTimeout(tick, FOLLOW_UP_DELAY_MS);
        followUpTimers.set(workspaceId, timer);
      }
    };
    const timer = setTimeout(tick, FOLLOW_UP_DELAY_MS);
    followUpTimers.set(workspaceId, timer);
  };

  const scheduleRoutine = (only?: ReadonlySet<string>) => {
    if (disposed) return;
    if (!scope || !scope.enabled) {
      clearRoutine();
      clearFollowUps();
      cumulative.clear();
      return;
    }
    const workspaces = new Set<string>();
    for (const agent of agents.values()) {
      if (!agent.workspaceId || agent.archived || agent.background) continue;
      if (inScope(agent.workspaceId)) workspaces.add(agent.workspaceId);
    }
    for (const workspaceId of workspaces) {
      if (only && !only.has(workspaceId)) continue;
      if (routineTimers.has(workspaceId)) continue;
      // A routine non-refresh read could return the server's short cache and
      // undo a fresher follow-up, so the chain owns the workspace meanwhile.
      if (followUpTimers.has(workspaceId)) continue;
      const wait = Math.max(0, CUMULATIVE_MIN_INTERVAL_MS - (Date.now() - (lastRequest.get(workspaceId) ?? 0)));
      const timer = setTimeout(() => {
        routineTimers.delete(workspaceId);
        if (followUpTimers.has(workspaceId)) return;
        requestCumulative(workspaceId, false);
      }, wait);
      routineTimers.set(workspaceId, timer);
    }
    for (const [workspaceId, timer] of routineTimers) {
      if (workspaces.has(workspaceId)) continue;
      clearTimeout(timer);
      routineTimers.delete(workspaceId);
      cumulative.delete(workspaceId);
    }
  };

  /**
   * Any change to who belongs to a workspace invalidates the displayed value
   * and everything still in flight for it, then starts one fresh read.
   */
  const syncMembers = (): Set<string> => {
    const changed = new Set<string>();
    const next = new Map<string, string>();
    for (const agent of agents.values()) {
      const target = pillTargetFor(agent);
      if (!target) continue;
      const list = next.get(target.workspaceId);
      next.set(target.workspaceId, list === undefined ? target.id : list + "," + target.id);
    }
    for (const workspaceId of new Set([...members.keys(), ...next.keys()])) {
      const before = members.get(workspaceId);
      const after = next.get(workspaceId);
      if (before === after) continue;
      changed.add(workspaceId);
      memberVersions.set(workspaceId, (memberVersions.get(workspaceId) ?? 0) + 1);
      cumulative.delete(workspaceId);
      // A changed but still visible member set keeps its chain: in-flight
      // responses are already voided by the member version, and each tick
      // reads the members that exist then. Only an empty workspace stops it.
      if (after === undefined) clearFollowUps(workspaceId);
      if (after === undefined) members.delete(workspaceId);
      else members.set(workspaceId, after);
    }
    return changed;
  };

  const applyAgents = (affected?: ReadonlySet<string>) => {
    const changed = syncMembers();
    reconcile();
    const touched = new Set<string>(affected ?? []);
    for (const workspaceId of changed) touched.add(workspaceId);
    scheduleRoutine(touched.size > 0 ? touched : undefined);
  };

  /**
   * A finished turn is signalled either by running -> terminal, or by a new
   * public `updatedAt` while the agent is already terminal (the turn ended
   * between two directory snapshots).
   */
  const noteStatus = (
    workspaceId: string | null,
    previous: { status: string | null; updatedAt: string | null } | undefined,
    next: DirectoryAgent,
  ) => {
    if (!workspaceId || next.status === null || !TERMINAL_STATUSES.has(next.status)) return;
    // Only a visible, in-scope conversation can contribute to the label.
    if (!inScope(workspaceId) || pillTargetFor(next) === null) return;
    if (previous === undefined) return;
    const leftRunning = previous.status === "running";
    const terminalRefresh = previous.status !== null &&
      TERMINAL_STATUSES.has(previous.status) &&
      previous.updatedAt !== null &&
      next.updatedAt !== null &&
      previous.updatedAt !== next.updatedAt;
    if (leftRunning || terminalRefresh) scheduleFollowUp(workspaceId);
  };

  const upsert = (source: AgentDirectoryEntry) => {
    const previous = agents.get(source.id);
    const agent = projectDirectoryAgent(source);
    agents.set(agent.id, agent);
    const affected = new Set<string>();
    if (previous?.workspaceId) affected.add(previous.workspaceId);
    if (agent.workspaceId) affected.add(agent.workspaceId);
    applyAgents(affected);
    noteStatus(agent.workspaceId, previous, agent);
  };

  const remove = (agentId: string) => {
    const previous = agents.get(agentId);
    agents.delete(agentId);
    applyAgents(previous?.workspaceId ? new Set([previous.workspaceId]) : undefined);
  };

  const unsubscribeAgents = deps.subscribeAgents({
    snapshot(entries) {
      const previous = new Map(agents);
      agents.clear();
      for (const entry of entries) {
        const projected = projectDirectoryAgent(entry);
        agents.set(projected.id, projected);
      }
      for (const [id, agent] of agents) {
        noteStatus(agent.workspaceId, previous.get(id), agent);
      }
      applyAgents();
    },
    update(message) {
      if (message.type !== "agent_update") return;
      const payload = message.payload;
      if (payload.kind === "remove") {
        if (payload.agentId) remove(payload.agentId);
        return;
      }
      if (payload.agent) upsert(payload.agent);
    },
  });

  let releaseSettings: () => void;
  let settingsRetry: ReturnType<typeof setTimeout> | undefined;
  let settingsCloses = 0;

  // The host never replays a rejected or closed subscription (for example one
  // retried while the plugin is still loading after a daemon restart).
  const openSettings = () => {
    releaseSettings = deps.subscribeSettings({
      next(event) {
        if (disposed) return;
        settingsCloses = 0;
        generation += 1;
        scope = event;
        cumulative.clear();
        lastRequest.clear();
        clearRoutine();
        clearFollowUps();
        reconcile();
        scheduleRoutine();
      },
      closed() {
        if (disposed) return;
        generation += 1;
        scope = EMPTY_SCOPE;
        cumulative.clear();
        clearRoutine();
        clearFollowUps();
        reconcile();
        scheduleRoutine();
        const delay = SETTINGS_RETRY_DELAYS_MS[Math.min(settingsCloses, SETTINGS_RETRY_DELAYS_MS.length - 1)];
        settingsCloses += 1;
        settingsRetry = setTimeout(() => {
          releaseSettings();
          openSettings();
        }, delay);
      },
    });
  };
  openSettings();

  return {
    dispose() {
      if (disposed) return;
      disposed = true;
      generation += 1;
      clearRoutine();
      clearFollowUps();
      unsubscribeAgents();
      clearTimeout(settingsRetry);
      releaseSettings();
      for (const pill of pills.values()) pill.handle.remove();
      pills.clear();
      agents.clear();
      cumulative.clear();
    },
  };
}
