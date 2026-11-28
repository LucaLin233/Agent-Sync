import { useSyncExternalStore } from "react";
import { scopeQueryKey, type WorkspaceScope } from "../shared/scope.ts";

/**
 * The small amount of state the bundle runtime and the host-rendered composer
 * pill must agree on without either owning the other:
 *
 * - the effective scope, so a settings change gates the pill's read at once;
 * - the manual/terminal refresh revision, part of the shared cumulative query
 *   key, so one refresh bumps both surfaces of that workspace and they stay
 *   one request — without re-keying a different workspace's label;
 * - whether a surface already owns a workspace's cumulative read. While it
 *   does, the runtime's own timer-driven reads become revision bumps instead of
 *   a second RPC, so the read never depends on a timer firing.
 */
export type SharedScopeStatus = "pending" | "live" | "failed";
/**
 * Who published the current scope. The runtime's own settings stream (and its
 * direct scope read) are `runtime`; an open panel's copy of the same event is
 * `panel`. It only decides who may adopt an event, never which one wins.
 */
export type SharedScopeSource = "runtime" | "panel";

export interface SharedStore {
  scope(): WorkspaceScope | null;
  scopeStatus(): SharedScopeStatus;
  /**
   * Publishes the effective scope. `fresh` is the single settings-stream owner
   * saying "this event starts a new read"; scope and revision then move in one
   * commit so a surface renders once and issues one request. Every other
   * publisher (another subscription's copy of the same event, or a surface's
   * first scope) never bumps, so one settings change stays one key.
   */
  setScope(
    scope: WorkspaceScope | null,
    status: SharedScopeStatus,
    fresh?: boolean,
    source?: SharedScopeSource,
  ): void;
  /** Who published the current scope; a runtime's own publish is not adopted. */
  scopeSource(): SharedScopeSource;
  /**
   * Whether the runtime's own settings subscription currently has a delivered
   * event. While it does, that stream owns the scope and a panel's copy of the
   * same event must not publish a second one. While it does not (no first value
   * yet, or closed), a panel's event is the only real settings and may.
   */
  runtimeStreamLive(): boolean;
  setRuntimeStreamLive(live: boolean): void;
  /** The settings generation, bumped once per event that changed the scope. */
  revision(): number;
  /** One workspace's refresh revision; other workspaces keep their own key. */
  workspaceRevision(workspaceId: string): number;
  /**
   * Starts a fresh read of one workspace; `refresh` also bypasses the server's
   * short cache. Only that workspace's surfaces move key, so a refresh or a
   * finished turn in A never re-reads B.
   */
  bumpWorkspace(workspaceId: string, refresh?: boolean): void;
  /**
   * Whether the bump that produced `revision` asked for a cache-bypassing read.
   * A later key (for example a changed member set) reads the server's cache
   * again instead of inheriting an old manual refresh forever.
   */
  refreshIntent(workspaceId: string, revision: number): boolean;
  surfaceOwns(workspaceId: string): boolean;
  claimSurface(workspaceId: string): () => void;
  subscribe(listener: () => void): () => void;
}

export function createSharedStore(): SharedStore {
  let scope: WorkspaceScope | null = null;
  let status: SharedScopeStatus = "pending";
  let revision = 0;
  let runtimeLive = false;
  let source: SharedScopeSource = "runtime";
  // One refresh revision per workspace: a refresh or a finished turn in one
  // workspace moves that workspace's key and nothing else's.
  const workspaceRevisions = new Map<string, number>();
  const bypassAt = new Map<string, number>();
  const surfaces = new Map<string, number>();
  const listeners = new Set<() => void>();
  const notify = () => {
    for (const listener of listeners) listener();
  };
  return {
    scope: () => scope,
    scopeStatus: () => status,
    runtimeStreamLive: () => runtimeLive,
    setRuntimeStreamLive(live) {
      if (runtimeLive === live) return;
      runtimeLive = live;
      notify();
    },
    scopeSource: () => source,
    setScope(next, nextStatus, fresh = false, nextSource = "runtime") {
      // A duplicate copy of a settings event is a no-op; the one owner's
      // `fresh` call still advances the revision so an identical projection
      // gets its fresh read, and it does it in the same commit as the scope.
      if (!fresh && next === scope && nextStatus === status) return;
      // A settings event can change what a read returns without changing the
      // projection (a changed Codex home, for example), so `fresh` forces a new
      // revision even then. Both are published together, so no surface ever
      // observes the new scope under the old revision.
      scope = next;
      status = nextStatus;
      source = nextSource;
      if (fresh) {
        revision += 1;
        bypassAt.clear();
      }
      notify();
    },
    revision: () => revision,
    workspaceRevision: (workspaceId) => workspaceRevisions.get(workspaceId) ?? 0,
    bumpWorkspace(workspaceId, bypass = false) {
      const next = (workspaceRevisions.get(workspaceId) ?? 0) + 1;
      workspaceRevisions.set(workspaceId, next);
      if (bypass) bypassAt.set(workspaceId, next);
      notify();
    },
    refreshIntent: (workspaceId, at) => bypassAt.get(workspaceId) === at,
    surfaceOwns: (workspaceId) => (surfaces.get(workspaceId) ?? 0) > 0,
    claimSurface(workspaceId) {
      // Several pills (one per agent) can observe one workspace; only the last
      // unmount releases the workspace back to the runtime's own reads, so the
      // runtime hears every transition and can resume reading what nobody
      // observes anymore.
      surfaces.set(workspaceId, (surfaces.get(workspaceId) ?? 0) + 1);
      notify();
      let released = false;
      return () => {
        if (released) return;
        released = true;
        const left = (surfaces.get(workspaceId) ?? 0) - 1;
        if (left > 0) surfaces.set(workspaceId, left);
        else surfaces.delete(workspaceId);
        notify();
      };
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}

/**
 * A settings event an open panel received on its own stream.
 *
 * The runtime and the panel each subscribe; either one can be the first, or
 * the only, subscriber that survives. While the runtime's own stream delivers,
 * it owns the scope: the panel's copy is the same event, and publishing it
 * would move the key twice. Otherwise (no first value yet, or the stream
 * closed) the panel's event is the real settings, and it is published as the
 * one owner of this generation — a fresh revision — so the runtime adopts it
 * without publishing again, and every surface still moves key exactly once.
 */
export function publishPanelScope(store: SharedStore, event: WorkspaceScope): void {
  if (store.runtimeStreamLive()) return;
  // A live scope with the same read identity is already in force (a reconnected
  // panel delivering its previous event, or a scope the runtime resolved
  // itself). Re-keying then would start a read nobody's settings changed for.
  // A pending or failed placeholder is not a decision even when it happens to
  // look identical (a closed stream's empty scope), so the panel's real event
  // still replaces it and marks the scope live.
  const current = store.scope();
  if (
    store.scopeStatus() === "live" &&
    current !== null &&
    scopeQueryKey(current) === scopeQueryKey(event)
  ) {
    return;
  }
  store.setScope(event, "live", true, "panel");
}

/** The scope the runtime learned; `null` until it has one. */
export function useSharedScope(store: SharedStore): WorkspaceScope | null {
  return useSyncExternalStore(store.subscribe, store.scope, store.scope);
}

/** How the runtime's scope stands: unresolved, live, or its stream failed. */
export function useSharedScopeStatus(store: SharedStore): SharedScopeStatus {
  return useSyncExternalStore(store.subscribe, store.scopeStatus, store.scopeStatus);
}

/** The settings generation, part of every surface's cumulative query key. */
export function useSharedRevision(store: SharedStore): number {
  return useSyncExternalStore(store.subscribe, store.revision, store.revision);
}

/** One workspace's refresh revision; a refresh of A leaves B untouched. */
export function useWorkspaceRevision(store: SharedStore, workspaceId: string): number {
  return useSyncExternalStore(
    store.subscribe,
    () => store.workspaceRevision(workspaceId),
    () => store.workspaceRevision(workspaceId),
  );
}
