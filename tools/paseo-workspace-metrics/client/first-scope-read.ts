import type { WorkspaceScope } from "../shared/scope.ts";
import { settingsRetryDelayMs } from "./subscription-retry.ts";

/** Attempts of the pill surface's own scope read; the runtime keeps its own path. */
export const FIRST_SCOPE_ATTEMPTS = 3;

export interface FirstScopeReadDeps {
  read(): Promise<WorkspaceScope>;
  /** Hands the scope to the single runtime; `false` means the runtime already owns one. */
  adopt(scope: WorkspaceScope): boolean;
  /** Whether the runtime already holds a scope; then no surface read is needed. */
  settled(): boolean;
  schedule(callback: () => void, delayMs: number): { cancel(): void };
}

/**
 * The composer pill icon's first read. It only resolves and hands over the
 * scope: members, single-flight cumulative reads and the shared label stay in
 * the bundle runtime. A failed read retries on the same backoff as the settings
 * stream, a bounded number of times, so one transport error cannot leave this
 * mount without a scope for good.
 */
export function readFirstScope(deps: FirstScopeReadDeps): () => void {
  let cancelled = false;
  let timer: { cancel(): void } | undefined;
  const attempt = (index: number) => {
    if (cancelled || deps.settled()) return;
    void deps.read().then((scope) => {
      if (cancelled) return;
      // An adopted scope ends this read; a rejected one means the runtime
      // already has a newer scope (or is gone), so the surface stays out of it.
      deps.adopt(scope);
    }, () => {
      if (cancelled || index + 1 >= FIRST_SCOPE_ATTEMPTS) return;
      timer = deps.schedule(() => {
        timer = undefined;
        attempt(index + 1);
      }, settingsRetryDelayMs(index));
    });
  };
  attempt(0);
  return () => {
    cancelled = true;
    timer?.cancel();
    timer = undefined;
  };
}
