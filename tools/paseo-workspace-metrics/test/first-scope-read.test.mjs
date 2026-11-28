import assert from "node:assert/strict";
import { test } from "node:test";
import { FIRST_SCOPE_ATTEMPTS, readFirstScope } from "../client/first-scope-read.ts";

const WS = "wks_cold";
const scope = (patch = {}) => ({
  enabled: true, workspaceIds: [WS], allWorkspaces: false,
  codexHomeConfigured: true, error: null, ...patch,
});

function timers() {
  const pending = [];
  return {
    pending,
    schedule(callback, delayMs) {
      const entry = { callback, delayMs, cancelled: false };
      pending.push(entry);
      return {
        cancel() { entry.cancelled = true; },
      };
    },
    run() {
      const entry = pending.shift();
      if (!entry || entry.cancelled) return false;
      entry.callback();
      return true;
    },
  };
}

const settle = () => new Promise((resolve) => setImmediate(resolve));

test("a cold-start pill surface hands its scope to the one runtime", async () => {
  const adopted = [];
  const timer = timers();
  readFirstScope({
    read: async () => scope(),
    adopt: (event) => { adopted.push(event); return true; },
    settled: () => false,
    schedule: timer.schedule,
  });
  await settle();
  assert.deepEqual(adopted, [scope()]);
  assert.equal(timer.pending.length, 0);
});

test("a transport failure retries on the settings backoff and stops at the cap", async () => {
  const timer = timers();
  let reads = 0;
  readFirstScope({
    read: async () => { reads += 1; throw new Error("scope rpc down"); },
    adopt: () => { throw new Error("must not adopt a failure"); },
    settled: () => false,
    schedule: timer.schedule,
  });
  await settle();
  assert.equal(reads, 1);
  assert.equal(timer.pending[0].delayMs, 1_000);
  timer.run();
  await settle();
  assert.equal(reads, 2);
  assert.equal(timer.pending[0].delayMs, 2_000);
  timer.run();
  await settle();
  assert.equal(reads, FIRST_SCOPE_ATTEMPTS);
  assert.equal(timer.pending.length, 0, "the cap ends the retries");
});

test("a scope the runtime already owns is not adopted and ends the surface read", async () => {
  const timer = timers();
  let adopted = 0;
  readFirstScope({
    read: async () => { throw new Error("late transport error"); },
    adopt: () => { adopted += 1; return false; },
    settled: () => false,
    schedule: timer.schedule,
  });
  await settle();
  // A failed read is not handed over at all; only a resolved scope reaches adopt.
  assert.equal(adopted, 0);

  const stopped = timers();
  let dispose;
  readFirstScope({
    read: async () => scope(),
    adopt: () => false,
    settled: () => false,
    schedule: stopped.schedule,
  });
  await settle();
  assert.equal(stopped.pending.length, 0);
  dispose?.();
});

test("dispose cancels a scheduled retry", async () => {
  const timer = timers();
  let reads = 0;
  const dispose = readFirstScope({
    read: async () => { reads += 1; throw new Error("down"); },
    adopt: () => true,
    settled: () => false,
    schedule: timer.schedule,
  });
  await settle();
  assert.equal(reads, 1);
  dispose();
  assert.equal(timer.run(), false);
  assert.equal(reads, 1);
});

test("a runtime that already holds a scope is never read by the surface", async () => {
  let reads = 0;
  let adopted = 0;
  const timer = timers();
  readFirstScope({
    read: async () => { reads += 1; return scope(); },
    adopt: () => { adopted += 1; return true; },
    settled: () => true,
    schedule: timer.schedule,
  });
  await settle();
  assert.equal(reads, 0);
  assert.equal(adopted, 0);
});
