import type { CumulativeUsage } from "../shared/cumulative.ts";
import { pillTargetFor, projectDirectoryAgent, type AgentDirectoryEntry, type DirectoryAgent } from "../shared/agents.ts";
import {
  formatPillLabel,
  formatPillTitle,
  type PillCacheBasis,
} from "../shared/metrics.ts";
import { scopeQueryKey, workspaceInScope, type WorkspaceScope } from "../shared/scope.ts";
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
      if (refresh) shared.bumpWorkspace(workspaceId, true);
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
   * Recovery of a scope that never arrived or was lost: the settings stream is
   * not the only source (the scope RPC may work while the stream is closed or
   * silent), so a failed read is retried on the same backoff instead of
   * leaving the label unknown until some surface happens to ask again.
   */
  let scopeTimer: ReturnType<typeof setTimeout> | undefined;
  let scopeAttempts = 0;
  let scopeInflight = false;
  /** The settings stream closed and its scope is only a placeholder. */
  let scopeLost = false;
  /**
   * The shared revision whose panel-published scope was already adopted. A
   * panel event bumps the revision exactly once, so this both adopts every new
   * panel event and keeps an unrelated notification (a surface claiming a
   * workspace, a refresh bump) from re-applying the same scope.
   */
  let adoptedPanelRevision = -1;
  /** Workspaces whose last composer pill unmounted since the last routine pass. */
  let ownedWorkspaces = new Set<string>();

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
    scopeLost = false;
    // A first scope a panel published was already applied by the panel (its
    // reading may be in the hub, or in flight): adopting it here is not a
    // settings change, so it must not be re-applied later as one.
    if (shared.scopeSource() === "panel") adoptedPanelRevision = shared.revision();
    shared.setScope(event, "live");
    reconcile();
    scheduleRoutine();
  };

  const cancelScopeRead = () => {
    if (scopeTimer !== undefined) clearTimeout(scopeTimer);
    scopeTimer = undefined;
  };

  /**
   * A scope from the direct read. While the settings stream is healthy it owns
   * the scope, so a reply that merely repeats it changes nothing. Without it —
   * no first event yet, or a closed stream — this is the recovery path: a first
   * scope, a changed projection, or the same projection coming back after the
   * stream failed, which restores the settings generation.
   */
  const adoptScopeRead = (event: WorkspaceScope) => {
    if (scope === null) {
      takeInitialScope(event);
      return;
    }
    // A live settings stream owns the scope: a direct read that arrives after
    // its event is older information and must not replace it.
    if (!scopeLost) return;
    // The stream failed. A working scope RPC is the recovery path: its reply
    // restores the generation exactly like a settings event would.
    applyScope(event);
  };

  /**
   * One direct scope read, retried on the settings backoff until it answers or
   * the settings stream takes over again. The settings stream is not assumed
   * to be deliverable: on a cold start it may never produce a first event, and
   * a closed stream is only reopened by a later retry, so this read is the
   * liveness path for the label.
   */
  const requestScopeRead = () => {
    if (disposed || scopeInflight) return;
    cancelScopeRead();
    scopeInflight = true;
    deps.requestScope().then((event) => {
      scopeInflight = false;
      if (disposed) return;
      scopeAttempts = 0;
      adoptScopeRead(event);
    }).catch(() => {
      scopeInflight = false;
      if (disposed) return;
      // A live scope from the settings stream wins; only an unknown or lost
      // one needs this read to keep trying.
      if (scope !== null && !scopeLost) return;
      const delay = settingsRetryDelayMs(scopeAttempts);
      scopeAttempts += 1;
      scopeTimer = setTimeout(requestScopeRead, delay);
    });
  };

  /**
   * One settings generation: every surface read of it is voided and re-issued.
   *
   * `fresh` publishes this event as the settings-stream owner would: it bumps
   * the shared revision and moves every surface's key. A panel's event was
   * already published by the panel, which owns that generation, so it is
   * adopted with `fresh: false`: the runtime clears and re-reads under it, but
   * the same settings event does not re-key every surface a second time.
   */
  const applyScope = (event: WorkspaceScope, fresh = true) => {
    generation += 1;
    scope = event;
    // Clear the placeholder marker before publishing: the publish notifies the
    // shared subscription synchronously, and this event is now the real scope,
    // so it must not be adopted a second time from inside its own notification.
    scopeLost = false;
    inflight.clear();
    queued.clear();
    // A settings generation change drops what the old scope showed. This must
    // happen before the scope is published: publishing notifies subscribers
    // synchronously (a surface can start its read for the new key right away),
    // and clearing afterwards would void that new generation's first reply.
    hub.clearAll();
    // While this stream delivers, the runtime owns the settings generation and
    // bumps the shared revision once per event; the panel's copy is skipped. A
    // panel-owned event is adopted below with `fresh: false` instead. Either
    // way one settings change is one new key and one request.
    shared.setScope(event, "live", fresh);
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
        // This stream is live again: it owns the scope over a panel's copy.
        shared.setRuntimeStreamLive(true);
        // The stream is delivering again, so its own retry chain is the only
        // one needed; a pending direct read stops here.
        cancelScopeRead();
        scopeAttempts = 0;
        // A panel already established exactly this settings while this stream
        // was down, and the runtime adopted it. Reopening the stream confirms
        // the same read identity: it must not void the label or re-key the
        // shared read. Any other event is a real settings change.
        if (
          scope !== null &&
          !scopeLost &&
          shared.scopeSource() === "panel" &&
          scopeQueryKey(scope) === scopeQueryKey(event)
        ) {
          return;
        }
        scopeLost = false;
        applyScope(event);
      },
      closed() {
        if (disposed) return;
        shared.setRuntimeStreamLive(false);
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
        // The stream is down, but the scope RPC may still work: its retries run
        // alongside the reopening subscription, so a working backend recovers
        // the label without waiting for a stream that may never reopen.
        scopeLost = true;
        requestScopeRead();
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
    if (disposed) return;
    const event = shared.scope();
    if (scope === null) {
      if (event) takeInitialScope(event);
      return;
    }
    // A live scope published by a panel's own stream (this runtime's stream is
    // down) is adopted like a settings event. The source mark is what keeps a
    // runtime publish from being adopted by its own notification; and adopting
    // every panel event, not only the first, keeps a later change from being
    // masked by an earlier one.
    const panelOwns = event && shared.scopeStatus() === "live" && shared.scopeSource() === "panel";
    if (panelOwns && shared.revision() !== adoptedPanelRevision) {
      adoptedPanelRevision = shared.revision();
      scopeAttempts = 0;
      cancelScopeRead();
      // The panel already published this event; adopting it must not bump the
      // shared revision and start a second read of the same settings change.
      applyScope(event, false);
      return;
    }
    // Ownership is per workspace. When the last composer pill of a workspace
    // unmounts, its shared query stops, so the runtime takes that workspace
    // back on its own schedule; other workspaces are untouched.
    const owned = new Set<string>();
    for (const agent of agents.values()) {
      if (!agent.workspaceId || agent.archived || agent.background) continue;
      if (shared.surfaceOwns(agent.workspaceId)) owned.add(agent.workspaceId);
    }
    const resumed = new Set<string>();
    for (const workspaceId of ownedWorkspaces) {
      if (!owned.has(workspaceId)) resumed.add(workspaceId);
    }
    ownedWorkspaces = owned;
    if (resumed.size > 0) scheduleRoutine(resumed);
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
      if (disposed) return false;
      if (scope !== null && !scopeLost) return false;
      adoptScopeRead(event);
      cancelScopeRead();
      scopeAttempts = 0;
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
      cancelScopeRead();
      releaseSettings();
      for (const pill of pills.values()) pill.handle.remove();
      pills.clear();
      agents.clear();
    },
  };
}
