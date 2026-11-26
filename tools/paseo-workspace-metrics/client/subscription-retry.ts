/**
 * Waits before reopening a closed settings subscription; the last one repeats.
 * The composer pill and the panel share this schedule.
 */
export const SETTINGS_RETRY_DELAYS_MS = [1_000, 2_000, 5_000, 10_000, 30_000];

export function settingsRetryDelayMs(closes: number): number {
  return SETTINGS_RETRY_DELAYS_MS[Math.min(closes, SETTINGS_RETRY_DELAYS_MS.length - 1)];
}

export interface SubscriptionRetryTimers {
  /** Runs `callback` after `delayMs`; `cancel` drops it if it has not run. */
  schedule(callback: () => void, delayMs: number): { cancel(): void };
  /** Reopens the subscription. */
  retry(): void;
}

/**
 * The host never replays a rejected or closed subscription (for example one
 * opened while the plugin is still loading after a daemon restart), so every
 * close schedules a reopen on its own. Only one retry is pending at a time; the
 * next close, after that retry has been made, waits one step longer. An event
 * proves the subscription works and resets the backoff; dispose drops a pending
 * retry.
 */
export function createSubscriptionRetry(timers: SubscriptionRetryTimers) {
  let closes = 0;
  let pending: { cancel(): void } | undefined;
  const cancel = () => {
    pending?.cancel();
    pending = undefined;
  };
  return {
    closed() {
      if (pending) return;
      pending = timers.schedule(() => {
        pending = undefined;
        timers.retry();
      }, settingsRetryDelayMs(closes));
      closes += 1;
    },
    opened() {
      cancel();
      closes = 0;
    },
    dispose() {
      cancel();
    },
  };
}
