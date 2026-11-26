import assert from "node:assert/strict";
import { test } from "node:test";
import { createSubscriptionRetry, settingsRetryDelayMs } from "../client/subscription-retry.ts";
import { workspaceSettingsSubscription } from "../shared/scope.ts";

/** A scheduled retry that records its delay and can actually be cancelled. */
function fakeTimers(t) {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const scheduled = [];
  const cancelled = [];
  const retries = [];
  return {
    scheduled,
    cancelled,
    retries,
    deps: {
      schedule(callback, delayMs) {
        const id = scheduled.length;
        scheduled.push({ id, delayMs });
        const timer = setTimeout(callback, delayMs);
        return { cancel: () => { cancelled.push(id); clearTimeout(timer); } };
      },
      retry: () => retries.push(Date.now()),
    },
  };
}

test("retries wait 1/2/5/10/30 seconds and repeat the last step", () => {
  assert.deepEqual(
    [0, 1, 2, 3, 4, 5, 9].map(settingsRetryDelayMs),
    [1_000, 2_000, 5_000, 10_000, 30_000, 30_000, 30_000],
  );
});

test("a closed settings subscription is reopened after the backoff delay", (t) => {
  const fake = fakeTimers(t);
  const retry = createSubscriptionRetry(fake.deps);

  // The gap: a rejected or closed subscription is never replayed by the host,
  // so without a retry the panel kept its stale scope forever.
  retry.closed();
  assert.equal(fake.scheduled.length, 1);
  assert.equal(fake.scheduled[0].delayMs, 1_000);
  t.mock.timers.tick(999);
  assert.equal(fake.retries.length, 0);
  t.mock.timers.tick(1);
  assert.equal(fake.retries.length, 1);
});

test("each failed retry waits one step longer, and only one retry is pending", (t) => {
  const fake = fakeTimers(t);
  const retry = createSubscriptionRetry(fake.deps);
  let fired = 0;
  for (const delay of [1_000, 2_000, 5_000, 10_000, 30_000, 30_000]) {
    retry.closed();
    // A second close while the retry is still pending must not stack a timer.
    retry.closed();
    assert.equal(fake.scheduled.length, fired + 1);
    assert.equal(fake.scheduled.at(-1).delayMs, delay);
    t.mock.timers.tick(delay - 1);
    assert.equal(fake.retries.length, fired);
    t.mock.timers.tick(1);
    fired += 1;
    assert.equal(fake.retries.length, fired);
  }
  assert.deepEqual(fake.scheduled.map((entry) => entry.delayMs), [1_000, 2_000, 5_000, 10_000, 30_000, 30_000]);
  assert.deepEqual(fake.cancelled, []);
});

test("an event resets the backoff and cancels a pending retry", (t) => {
  const fake = fakeTimers(t);
  const retry = createSubscriptionRetry(fake.deps);
  retry.closed();
  retry.closed();
  retry.opened();
  assert.deepEqual(fake.cancelled, [0]);
  t.mock.timers.tick(60_000);
  assert.equal(fake.retries.length, 0);
  retry.closed();
  assert.equal(fake.scheduled.at(-1).delayMs, 1_000);
  t.mock.timers.tick(1_000);
  assert.equal(fake.retries.length, 1);
});

test("dispose cancels the pending retry", (t) => {
  const fake = fakeTimers(t);
  const retry = createSubscriptionRetry(fake.deps);
  retry.closed();
  retry.dispose();
  assert.deepEqual(fake.cancelled, [0]);
  t.mock.timers.tick(60_000);
  assert.equal(fake.retries.length, 0);
});

test("the settings contract carries the retry attempt so the host re-subscribes", () => {
  assert.deepEqual(workspaceSettingsSubscription.input.parse({ attempt: 3 }), { attempt: 3 });
  assert.deepEqual(workspaceSettingsSubscription.input.parse({}), {});
});
