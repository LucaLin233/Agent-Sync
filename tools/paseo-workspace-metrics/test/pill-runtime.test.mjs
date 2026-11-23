import assert from "node:assert/strict";
import { test } from "node:test";
import { startPillRuntime } from "../client/pill-runtime.ts";

const WS = "wks_metrics";

function fakeClient() {
  const pills = new Map();
  const calls = [];
  let agentHandlers = null;
  let settingsHandlers = null;
  const pending = [];
  return {
    pills,
    calls,
    pending,
    deps: {
      addPill({ workspaceId, agentId, title, label, onPress }) {
        const pill = { workspaceId, agentId, title, label, onPress, removed: false };
        pills.set(agentId, pill);
        return {
          update(patch) {
            if (patch.title !== undefined) pill.title = patch.title;
            if (patch.label !== undefined) pill.label = patch.label;
          },
          remove() {
            pill.removed = true;
            pills.delete(agentId);
          },
        };
      },
      openPanel(workspaceId, agentId) {
        calls.push({ type: "openPanel", workspaceId, agentId });
      },
      requestCumulative(input) {
        calls.push({ type: "rpc", ...input });
        return new Promise((resolve, reject) => pending.push({ input, resolve, reject }));
      },
      subscribeAgents(handlers) {
        agentHandlers = handlers;
        return () => { agentHandlers = null; };
      },
      subscribeSettings(handlers) {
        settingsHandlers = handlers;
        return () => { settingsHandlers = null; };
      },
    },
    emitSnapshot(entries) {
      agentHandlers.snapshot(entries);
    },
    emitUpsert(agent) {
      agentHandlers.update({ type: "agent_update", payload: { kind: "upsert", agent } });
    },
    emitRemove(agentId) {
      agentHandlers.update({ type: "agent_update", payload: { kind: "remove", agentId } });
    },
    enable(patch = {}) {
      settingsHandlers.next({
        enabled: true,
        workspaceIds: [WS],
        allWorkspaces: false,
        codexHomeConfigured: true,
        error: null,
        ...patch,
      });
    },
  };
}

const agent = (id, extra = {}) => ({
  id,
  workspaceId: WS,
  provider: "codex",
  status: "idle",
  lastUsage: { inputTokens: 100, cachedInputTokens: 50 },
  ...extra,
});

const reply = (rate, outputTokens, elapsedMs) => ({
  workspaceId: WS,
  inputTokens: 100,
  cachedInputTokens: 50,
  covered: 1,
  eligible: 1,
  missing: 0,
  unavailable: 0,
  rate,
  error: null,
  recentTurn: outputTokens === null ? null : {
    completedAt: 1_000,
    outputTokens,
    elapsedMs,
    firstTokenMs: null,
  },
  turns: {
    sessions: 1, completed: 1, speedSamples: 1, firstTokenSamples: 0,
    outputTokens: 0, elapsedMs: 0, firstTokenTotalMs: 0,
  },
});

/** Flushes timers and the microtasks their callbacks queue. */
async function settle() {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  await new Promise((resolve) => setImmediate(resolve));
}

async function advance(t, ms) {
  t.mock.timers.tick(ms);
  await settle();
}

test("a terminal transition re-reads after the rollout flush without new directory events", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps);
  t.after(() => runtime.dispose());

  fake.enable();
  fake.emitSnapshot([agent("a", { status: "running" })]);
  await advance(t, 10_000);
  assert.equal(fake.pending.length, 1);
  fake.pending.shift().resolve(reply(0.25, 100, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "缓存 25.0% · 近轮 10.0 t/s");

  // The turn reaches a terminal state; the rollout it describes is not written yet.
  fake.emitUpsert(agent("a", { status: "idle" }));
  await advance(t, 0);
  assert.equal(fake.pending.length, 0, "no immediate read on an ordinary update");

  await advance(t, 1_200);
  assert.equal(fake.pending.length, 1);
  const followUp = fake.pending.shift();
  assert.deepEqual(followUp.input, { workspaceId: WS, agentIds: ["a"], refresh: true });
  followUp.resolve(reply(0.25, 600, 10_000));
  await advance(t, 0);

  // No further directory event: the follow-up alone moved the label.
  assert.equal(fake.pills.get("a").label, "缓存 25.0% · 近轮 60.0 t/s");
  assert.match(fake.pills.get("a").title, /打开工作区用量/);
  assert.match(fake.pills.get("a").title, /缓存 25\.0%/);
  assert.match(fake.pills.get("a").title, /近轮 60\.0 t\/s/);
});

test("a second terminal turn during the chain restores the budget for its rollout", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps);
  t.after(() => runtime.dispose());
  fake.enable();
  fake.emitSnapshot([agent("a", { status: "running" }), agent("b", { status: "running" })]);
  await advance(t, 10_000);
  fake.pending.shift().resolve(reply(0.25, 100, 10_000));
  await advance(t, 0);

  // A finishes first; its chain starts.
  fake.emitUpsert(agent("a", { status: "idle" }));
  await advance(t, 1_200);
  fake.pending.shift().resolve(reply(0.25, 100, 10_000));
  await advance(t, 1_200);
  fake.pending.shift().resolve(reply(0.25, 100, 10_000));
  await advance(t, 1_100);

  // B finishes 3.5 s after A, 0.2 s before that chain's last scheduled tick.
  fake.emitUpsert(agent("b", { status: "idle" }));
  await advance(t, 100);
  assert.equal(fake.pending.length, 1);
  // Its rollout is still old at that tick.
  fake.pending.shift().resolve(reply(0.25, 100, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "缓存 25.0% · 近轮 10.0 t/s");

  // No further directory events; the restored budget alone picks up B.
  await advance(t, 1_200);
  assert.equal(fake.pending.length, 1);
  assert.equal(fake.pending[0].input.refresh, true);
  fake.pending.shift().resolve(reply(0.25, 600, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "缓存 25.0% · 近轮 60.0 t/s");
  assert.equal(fake.pills.get("b").label, "缓存 25.0% · 近轮 60.0 t/s");
});

test("a member change keeps an active chain and reads the current members", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps);
  t.after(() => runtime.dispose());
  fake.enable();
  fake.emitSnapshot([agent("a", { status: "running" }), agent("b", { status: "running" })]);
  await advance(t, 10_000);
  fake.pending.shift().resolve(reply(0.25, 100, 10_000));
  await advance(t, 0);

  fake.emitUpsert(agent("a", { status: "idle" }));
  await advance(t, 1_200);
  const first = fake.pending.shift();
  assert.deepEqual(first.input.agentIds, ["a", "b"]);

  // B leaves while the read is in flight; A remains visible.
  fake.emitRemove("b");
  assert.equal(fake.pills.has("b"), false);
  first.resolve(reply(0.8, 800, 10_000));
  await advance(t, 0);
  // The stale [A,B] success is voided, and the chain is still alive.
  assert.equal(fake.pills.get("a").label, "缓存 …");

  await advance(t, 1_200);
  assert.equal(fake.pending.length, 1);
  assert.deepEqual(fake.pending[0].input, { workspaceId: WS, agentIds: ["a"], refresh: true });
  fake.pending.shift().resolve(reply(0.2, 200, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "缓存 20.0% · 近轮 20.0 t/s");
});

test("follow-up reads are bounded and stop", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps);
  t.after(() => runtime.dispose());
  fake.enable();
  fake.emitSnapshot([agent("a", { status: "running" })]);
  await advance(t, 10_000);
  fake.pending.shift().resolve(reply(0.25, 100, 10_000));
  await advance(t, 0);
  fake.emitUpsert(agent("a", { status: "closed" }));

  for (let round = 1; round <= 3; round += 1) {
    await advance(t, 1_200);
    assert.equal(fake.pending.length, 1, "round " + round);
    fake.pending.shift().resolve(reply(0.25, 500, 10_000));
    await advance(t, 0);
  }
  await advance(t, 1_200);
  assert.equal(fake.pending.length, 0);
  assert.equal(fake.calls.filter((call) => call.type === "rpc" && call.refresh).length, 3);
});

test("a turn that ended between snapshots still triggers one bounded re-read", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps);
  t.after(() => runtime.dispose());
  fake.enable();
  fake.emitSnapshot([agent("a", { status: "idle", updatedAt: "2026-11-22T00:00:00Z" })]);
  await advance(t, 10_000);
  fake.pending.shift().resolve(reply(0.2, 100, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "缓存 20.0% · 近轮 10.0 t/s");

  // Never observed as running: the new updatedAt is the only terminal signal.
  fake.emitUpsert(agent("a", { status: "idle", updatedAt: "2026-11-22T00:05:00Z" }));
  await advance(t, 1_200);
  assert.equal(fake.pending.length, 1);
  fake.pending.shift().resolve(reply(0.2, 500, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "缓存 20.0% · 近轮 50.0 t/s");
});

test("a routine read does not race the follow-up chain for the same workspace", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps);
  t.after(() => runtime.dispose());
  fake.enable();
  fake.emitSnapshot([agent("a", { status: "running" })]);
  await advance(t, 10_000);
  fake.pending.shift().resolve(reply(0.25, 100, 10_000));
  await advance(t, 0);

  fake.emitUpsert(agent("a", { status: "idle" }));
  await advance(t, 1_200);
  assert.equal(fake.pending.length, 1);
  fake.pending.shift().resolve(reply(0.25, 600, 10_000));
  await advance(t, 0);

  // The 10 s routine window elapses while the chain is still running: every
  // read issued in that interval must be a refresh, never the cached read.
  await advance(t, 1_200);
  assert.equal(fake.pending.length, 1);
  assert.equal(fake.pending[0].input.refresh, true);
  fake.pending.shift().resolve(reply(0.25, 600, 10_000));
  await advance(t, 0);
  await advance(t, 1_200);
  assert.equal(fake.pending.length, 1);
  assert.equal(fake.pending[0].input.refresh, true);
  fake.pending.shift().resolve(reply(0.25, 600, 10_000));
  await advance(t, 0);
  assert.equal(fake.calls.filter((call) => call.type === "rpc" && !call.refresh).length, 1);
});

test("a late reply for archived members cannot overwrite the current workspace", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps);
  t.after(() => runtime.dispose());
  fake.enable();
  fake.emitSnapshot([agent("a", { status: "running" }), agent("b")]);
  await advance(t, 10_000);
  const stale = fake.pending.shift();
  assert.deepEqual(stale.input.agentIds, ["a", "b"]);

  // B is archived while [A,B] is still in flight.
  fake.emitUpsert(agent("b", { archivedAt: "2026-11-22T00:00:00Z" }));
  assert.equal(fake.pills.has("b"), false);

  await advance(t, 10_000);
  const fresh = fake.pending.shift();
  assert.deepEqual(fresh.input.agentIds, ["a"]);
  fresh.resolve(reply(0.2, 200, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "缓存 20.0% · 近轮 20.0 t/s");

  // The older [A,B] reply lands last and must be discarded.
  stale.resolve(reply(0.8, 800, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "缓存 20.0% · 近轮 20.0 t/s");
});

test("same-member concurrent replies keep only the newest request", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps);
  t.after(() => runtime.dispose());
  fake.enable();
  fake.emitSnapshot([agent("a")]);
  await advance(t, 10_000);
  const first = fake.pending.shift();

  // A settings refresh starts a second read for the same member set.
  fake.enable();
  await advance(t, 10_000);
  const second = fake.pending.shift();
  second.resolve(reply(0.2, 200, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "缓存 20.0% · 近轮 20.0 t/s");

  first.resolve(reply(0.8, 800, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "缓存 20.0% · 近轮 20.0 t/s");
});

test("failures from a superseded request are ignored too", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps);
  t.after(() => runtime.dispose());
  fake.enable();
  fake.emitSnapshot([agent("a"), agent("b")]);
  await advance(t, 10_000);
  const stale = fake.pending.shift();
  fake.emitRemove("b");
  await advance(t, 10_000);
  fake.pending.shift().resolve(reply(0.2, 200, 10_000));
  await advance(t, 0);
  stale.reject(new Error("late failure"));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "缓存 20.0% · 近轮 20.0 t/s");
});

test("workspace migration and background flag recompute membership", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps);
  t.after(() => runtime.dispose());
  fake.enable({ allWorkspaces: true, workspaceIds: [] });
  fake.emitSnapshot([agent("a"), agent("b")]);
  await advance(t, 10_000);
  fake.pending.shift().resolve(reply(0.2, 200, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").workspaceId, WS);

  fake.emitUpsert(agent("a", { workspaceId: "wks_other" }));
  assert.equal(fake.pills.get("a").workspaceId, "wks_other");
  await advance(t, 10_000);
  const moved = fake.pending.shift();
  assert.equal(moved.input.workspaceId, "wks_other");
  assert.deepEqual(moved.input.agentIds, ["a"]);
  moved.resolve({ ...reply(0.4, 400, 10_000), workspaceId: "wks_other" });
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "缓存 40.0% · 近轮 40.0 t/s");

  fake.emitUpsert(agent("b", { background: true }));
  assert.equal(fake.pills.has("b"), false);
});

test("dispose cancels pending timers and unregisters pills", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps);
  fake.enable();
  fake.emitSnapshot([agent("a", { status: "running" })]);
  await advance(t, 10_000);
  fake.pending.shift().resolve(reply(0.2, 200, 10_000));
  await advance(t, 0);
  fake.emitUpsert(agent("a", { status: "idle" }));
  runtime.dispose();
  assert.equal(fake.pills.size, 0);
  await advance(t, 20_000);
  assert.equal(fake.calls.filter((call) => call.type === "rpc" && call.refresh).length, 0);
});
