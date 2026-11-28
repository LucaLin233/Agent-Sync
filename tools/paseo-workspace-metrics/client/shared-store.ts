import { useSyncExternalStore } from "react";
import type { WorkspaceScope } from "../shared/scope.ts";

/**
 * The small amount of state the bundle runtime and the host-rendered composer
 * pill must agree on without either owning the other:
 *
 * - the effective scope, so a settings change gates the pill's read at once;
 * - the manual/terminal refresh revision, part of the shared cumulative query
 *   key, so one refresh bumps both surfaces and they stay one request;
 * - whether a surface already owns a workspace's cumulative read. While it
 *   does, the runtime's own timer-driven reads become revision bumps instead of
 *   a second RPC, so the read never depends on a timer firing.
 */
export type SharedScopeStatus = "pending" | "live" | "failed";

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
  setScope(scope: WorkspaceScope | null, status: SharedScopeStatus, fresh?: boolean): void;
  revision(): number;
  /** Starts a fresh shared read; `refresh` also bypasses the server's short cache. */
  bump(refresh?: boolean): void;
  /**
   * Whether the bump that produced `revision` asked for a cache-bypassing read.
   * A later key (for example a changed member set) reads the server's cache
   * again instead of inheriting an old manual refresh forever.
   */
  refreshIntent(revision: number): boolean;
  surfaceOwns(workspaceId: string): boolean;
  claimSurface(workspaceId: string): () => void;
  subscribe(listener: () => void): () => void;
}

export function createSharedStore(): SharedStore {
  let scope: WorkspaceScope | null = null;
  let status: SharedScopeStatus = "pending";
  let revision = 0;
  let bypassAt = -1;
  const surfaces = new Map<string, number>();
  const listeners = new Set<() => void>();
  const notify = () => {
    for (const listener of listeners) listener();
  };
  return {
    scope: () => scope,
    scopeStatus: () => status,
    setScope(next, nextStatus, fresh = false) {
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
      if (fresh) {
        revision += 1;
        bypassAt = -1;
      }
      notify();
    },
    revision: () => revision,
    bump(bypass = false) {
      revision += 1;
      if (bypass) bypassAt = revision;
      notify();
    },
    refreshIntent: (at) => bypassAt === at,
    surfaceOwns: (workspaceId) => (surfaces.get(workspaceId) ?? 0) > 0,
    claimSurface(workspaceId) {
      // Several pills (one per agent) can observe one workspace; only the last
      // unmount releases the workspace back to the runtime's own reads.
      surfaces.set(workspaceId, (surfaces.get(workspaceId) ?? 0) + 1);
      let released = false;
      return () => {
        if (released) return;
        released = true;
        const left = (surfaces.get(workspaceId) ?? 0) - 1;
        if (left > 0) surfaces.set(workspaceId, left);
        else surfaces.delete(workspaceId);
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

/** The scope the runtime learned; `null` until it has one. */
export function useSharedScope(store: SharedStore): WorkspaceScope | null {
  return useSyncExternalStore(store.subscribe, store.scope, store.scope);
}

/** How the runtime's scope stands: unresolved, live, or its stream failed. */
export function useSharedScopeStatus(store: SharedStore): SharedScopeStatus {
  return useSyncExternalStore(store.subscribe, store.scopeStatus, store.scopeStatus);
}

/** The shared refresh revision, part of every surface's cumulative query key. */
export function useSharedRevision(store: SharedStore): number {
  return useSyncExternalStore(store.subscribe, store.revision, store.revision);
}
