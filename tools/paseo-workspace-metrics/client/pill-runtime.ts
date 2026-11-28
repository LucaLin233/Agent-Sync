import type { CumulativeUsage } from "../shared/cumulative.ts";
import { pillTargetFor, projectDirectoryAgent, type AgentDirectoryEntry, type DirectoryAgent } from "../shared/agents.ts";
import {
  formatPillLabel,
  formatPillTitle,
  type PillCacheBasis,
} from "../shared/metrics.ts";
import { workspaceInScope, type WorkspaceScope } from "../shared/scope.ts";
import type { CumulativeHub } from "./cumulative-hub.ts";
import { createSharedStore, type SharedStore } from "./shared-store.ts";
import { settingsRetryDelayMs } from "./subscription-retry.ts";

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
  /**
   * One direct read of the effective scope, independent of the settings stream.
   * A freshly loaded client may never receive that stream's first event; this
   * read still lets the pill learn its scope and start its own reads.
   */
  requestScope(): Promise<WorkspaceScope>;
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

/** Routine directory-driven reads stay at most one per this window per workspace. */
const CUMULATIVE_MIN_INTERVAL_MS = 10_000;
/** A finished turn may be flushed to its rollout after the directory update. */
const FOLLOW_UP_DELAY_MS = 1_200;
const FOLLOW_UP_LIMIT = 3;
const TERMINAL_STATUSES = new Set(["idle", "error", "closed"]);

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
export function startPillRuntime(
  deps: PillRuntimeDeps,
  hub: CumulativeHub,
  // One store per client in production; a standalone store keeps a runtime
  // that no surface observes self-contained.
  shared: SharedStore = createSharedStore(),
) {
  const agents = new Map<string, DirectoryAgent>();
  const pills = new Map<string, PillState>();
  const routineTimers = new Map<string, ReturnType<typeof setTimeout>>();
  const followUpTimers = new Map<string, ReturnType<typeof setTimeout>>();
  const followUpsLeft = new Map<string, number>();
  const lastRequest = new Map<string, number>();
  /** Bumped whenever the effective member set of a workspace changes. */
  const memberVersions = new Map<string, number>();
  /**
   * One read per workspace at a time. A demand that arrives while another read is
   * in flight coalesces into one follow-on read issued when the current one
   * settles, so overlapping reads never race each other into the host.
   */
  const inflight = new Map<string, { generation: number; task: Promise<void> }>();
  /** A pending follow-on read per workspace; `true` asks for a bypassing refresh. */
  const queued = new Map<string, boolean>();
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
    if (!scope) {
      // This client's settings stream has not produced its first event yet.
      // A reading the panel already obtained through its own settings stream
      // was validated by the backend for this workspace, so show it instead of
      // leaving the label on "…" until both streams happen to coincide. An
      // explicit disabled or out-of-allowlist scope below still wins.
      const shared = hub.read(workspaceId);
      if (!shared) return { kind: "loading" };
      if (shared.error) return { kind: "unavailable", reason: "累计读取失败：" + shared.error };
      return { kind: "ready", rate: shared.rate };
    }
    if (scope.error) return { kind: "unavailable", reason: "累计设置错误：" + scope.error };
    if (!scope.enabled) return { kind: "unavailable", reason: "累计统计已关闭" };
    if (!inScope(workspaceId)) return { kind: "unavailable", reason: "不在本机累计名单" };
    // The shared hub also carries results the panel obtained, so either entry
    // point publishing a valid reading updates this label.
    const reading = hub.read(workspaceId);
    if (!reading) return { kind: "loading" };
    if (reading.error) return { kind: "unavailable", reason: "累计读取失败：" + reading.error };
    return { kind: "ready", rate: reading.rate };
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

  /**
   * Issues one cumulative read, or coalesces the demand into the read already in
   * flight. Any reply from the current settings generation and member set may
   * land: an older in-flight read carrying a valid result is not voided just
   * because a newer read is queued. The hub only accepts replies newer than the
   * last adopted request signature, so a late older reply never overwrites
   * fresher data while a newer reply that returns second still replaces it.
   */
  const requestCumulative = (workspaceId: string, refresh: boolean) => {
    if (disposed) return;
    const agentIds = agentIdsFor(workspaceId);
    if (agentIds.length === 0) {
      members.delete(workspaceId);
      queued.delete(workspaceId);
      hub.clear(workspaceId);
      reconcile();
      return;
    }
    // A mounted composer pill owns this workspace's cumulative read through the
    // shared query key. Its own key already carries the member set, so routine
    // and member demands need no extra request; a terminal follow-up (or an
    // explicit bypass) asks both surfaces for one fresh revision instead.
    if (shared.surfaceOwns(workspaceId)) {
      if (refresh) shared.bump(true);
      return;
    }
    if (inflight.has(workspaceId)) {
      queued.set(workspaceId, (queued.get(workspaceId) ?? false) || refresh);
      return;
    }
    const version = memberVersions.get(workspaceId) ?? 0;
    const requestGeneration = generation;
    const ticket = hub.begin(workspaceId);
    lastRequest.set(workspaceId, Date.now());
    // A settings or member change still voids a reply; a merely newer request
    // does not, and overlapping reads are serialized per workspace.
    const live = () =>
      !disposed &&
      requestGeneration === generation &&
      version === (memberVersions.get(workspaceId) ?? 0);
    const task = deps
      .requestCumulative({ workspaceId, agentIds, refresh })
      .then((result) => {
        if (!live()) return;
        hub.publish(workspaceId, ticket, { rate: result.rate, error: result.error });
        reconcile();
      })
      .catch(() => {
        if (!live()) return;
        // Failure and success take the same ordering gate: only a reply newer
        // than the last adopted one can change what is shown.
        hub.publish(workspaceId, ticket, { rate: null, error: "累计用量读取失败" });
        reconcile();
      })
      .finally(() => {
        if (inflight.get(workspaceId)?.task === task) inflight.delete(workspaceId);
        // A settings change starts its own generation; the old reply that has
        // just settled must not drive reads for the new scope.
        if (requestGeneration !== generation || disposed) return;
        const pending = queued.get(workspaceId);
        queued.delete(workspaceId);
        if (pending === undefined) return;
        requestCumulative(workspaceId, pending);
      });
    inflight.set(workspaceId, { generation: requestGeneration, task });
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
    if (!scope) {
      // Scope still unknown: issue no reads of our own and keep readings the
      // panel already validated; the first settings event owns the next clear.
      clearRoutine();
      clearFollowUps();
      queued.clear();
      return;
    }
    if (!scope.enabled) {
      clearRoutine();
      clearFollowUps();
      queued.clear();
      hub.clearAll();
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
      hub.clear(workspaceId);
    }
  };

  /**
   * Any change to who belongs to a workspace invalidates everything still in
   * flight for it and schedules one fresh read. While that read is pending a
   * still-visible workspace keeps showing its last valid reading.
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
      // Seeing a workspace's members for the first time is not a member
      // change: no earlier set existed to void, and the panel may already hold
      // a reading, or a read in flight, for exactly those members.
      if (before !== undefined) {
        // A still-visible workspace keeps its last valid rate (a real zero
        // included) while the member-triggered re-read is pending. Loading,
        // empty, and failed readings have no valid rate to keep, and a
        // workspace that lost every visible member drops its state.
        const reading = hub.read(workspaceId);
        const keep = after !== undefined && reading !== undefined &&
          reading.rate !== null && reading.error === null;
        if (!keep) hub.clear(workspaceId);
        // Reads started before this member change must not land on the new set.
        // `invalidate` keeps the shown reading but voids those replies; the
        // in-flight read still serializes the follow-on read for current
        // members.
        else hub.invalidate(workspaceId);
      }
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

  // The panel publishes into the same hub, so its readings also move the label.
  const unsubscribeHub = hub.subscribeAll(() => reconcile());

  let releaseSettings: () => void;
  let settingsRetry: ReturnType<typeof setTimeout> | undefined;
  let settingsCloses = 0;

  /**
   * The first scope this runtime ever learns, from either startup path (its own
   * direct read, or the composer pill surface's read). It is not a settings
   * change: nothing was read under an earlier scope, and the panel may already
   * hold a valid reading in the shared hub. So it only takes the scope and lets
   * `scheduleRoutine` decide — which includes clearing when the scope is
   * disabled or excludes this workspace — instead of resetting the hub.
   */
  const takeInitialScope = (event: WorkspaceScope) => {
    scope = event;
    shared.setScope(event, "live");
    reconcile();
    scheduleRoutine();
  };

  /**
   * One direct scope read at startup. The settings stream owns the scope once
   * it produces its first event — a value or a close, both leave `scope`
   * non-null — so a reply arriving after that, or after dispose, is dropped
   * instead of overwriting the newer state.
   */
  const requestScopeRead = () => {
    deps.requestScope().then((event) => {
      if (disposed || scope !== null) return;
      takeInitialScope(event);
    }).catch(() => {
      // Without a settings event either, the label keeps its unknown state and
      // the settings subscription stays the only source, with its own retry.
    });
  };

  /** One settings generation: every surface read of it is voided and re-issued. */
  const applyScope = (event: WorkspaceScope) => {
    generation += 1;
    scope = event;
    // This runtime owns the settings stream, so it is the only publisher that
    // starts a fresh shared read. An open panel's copy of the same event only
    // publishes a scope (and usually matches what is already in force), so one
    // settings change is one new key and one request.
    shared.setScope(event, "live", true);
    inflight.clear();
    queued.clear();
    // A settings generation change drops what the old scope showed.
    hub.clearAll();
    lastRequest.clear();
    clearRoutine();
    clearFollowUps();
    reconcile();
    scheduleRoutine();
  };

  // The host never replays a rejected or closed subscription (for example one
  // retried while the plugin is still loading after a daemon restart).
  const openSettings = () => {
    releaseSettings = deps.subscribeSettings({
      next(event) {
        if (disposed) return;
        settingsCloses = 0;
        applyScope(event);
      },
      closed() {
        if (disposed) return;
        generation += 1;
        scope = EMPTY_SCOPE;
        shared.setScope(EMPTY_SCOPE, "failed");
        inflight.clear();
        queued.clear();
        hub.clearAll();
        clearRoutine();
        clearFollowUps();
        reconcile();
        scheduleRoutine();
        const delay = settingsRetryDelayMs(settingsCloses);
        settingsCloses += 1;
        settingsRetry = setTimeout(() => {
          releaseSettings();
          openSettings();
        }, delay);
      },
    });
  };
  // The panel publishes the scope its own settings stream resolved, and a
  // surface may publish one it read itself. Whichever arrives first is this
  // runtime's first scope; later settings events still take the change path.
  const unsubscribeShared = shared.subscribe(() => {
    if (disposed || scope !== null) return;
    const event = shared.scope();
    if (event) takeInitialScope(event);
  });
  openSettings();
  requestScopeRead();

  return {
    /**
     * Adopts a scope the composer pill's own surface read, when the runtime has
     * not learned one yet. It is a first scope, not a settings change: nothing
     * was read under an earlier scope and the panel may already hold a reading,
     * so it takes the scope and lets `scheduleRoutine` decide (including
     * clearing a disabled or out-of-allowlist workspace) instead of resetting.
     * `false` means the runtime or its settings stream already owns the scope.
     */
    adoptScope(event: WorkspaceScope): boolean {
      if (disposed || scope !== null) return false;
      takeInitialScope(event);
      return true;
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      generation += 1;
      inflight.clear();
      queued.clear();
      clearRoutine();
      clearFollowUps();
      unsubscribeAgents();
      unsubscribeHub();
      unsubscribeShared();
      clearTimeout(settingsRetry);
      releaseSettings();
      for (const pill of pills.values()) pill.handle.remove();
      pills.clear();
      agents.clear();
    },
  };
}
