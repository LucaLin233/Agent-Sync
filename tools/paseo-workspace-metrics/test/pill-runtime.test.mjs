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
  const settings = { opened: 0, released: 0 };
  return {
    settings,
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
        settings.opened += 1;
        return () => { settingsHandlers = null; settings.released += 1; };
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
    closeSettings() {
      settingsHandlers.closed();
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
  assert.equal(fake.pills.get("a").label, "25.0%");

  // The turn reaches a terminal state; the rollout it describes is not written yet.
  fake.emitUpsert(agent("a", { status: "idle" }));
  await advance(t, 0);
  assert.equal(fake.pending.length, 0, "no immediate read on an ordinary update");

  await advance(t, 1_200);
  assert.equal(fake.pending.length, 1);
  const followUp = fake.pending.shift();
  assert.deepEqual(followUp.input, { workspaceId: WS, agentIds: ["a"], refresh: true });
  followUp.resolve(reply(0.6, 600, 10_000));
  await advance(t, 0);

  // No further directory event: the follow-up alone moved the cumulative slot.
  assert.equal(fake.pills.get("a").label, "60.0%");
  assert.equal(fake.pills.get("a").title,
    "打开工作区用量 · 累计缓存 60.0%");
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
  assert.equal(fake.pills.get("a").label, "25.0%");

  // No further directory events; the restored budget alone picks up B.
  await advance(t, 1_200);
  assert.equal(fake.pending.length, 1);
  assert.equal(fake.pending[0].input.refresh, true);
  fake.pending.shift().resolve(reply(0.6, 600, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "60.0%");
  assert.equal(fake.pills.get("b").label, "60.0%");
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
  assert.equal(fake.pills.get("a").label, "…");

  await advance(t, 1_200);
  assert.equal(fake.pending.length, 1);
  assert.deepEqual(fake.pending[0].input, { workspaceId: WS, agentIds: ["a"], refresh: true });
  fake.pending.shift().resolve(reply(0.2, 200, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "20.0%");
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
  assert.equal(fake.pills.get("a").label, "20.0%");

  // Never observed as running: the new updatedAt is the only terminal signal.
  fake.emitUpsert(agent("a", { status: "idle", updatedAt: "2026-11-22T00:05:00Z" }));
  await advance(t, 1_200);
  assert.equal(fake.pending.length, 1);
  fake.pending.shift().resolve(reply(0.5, 500, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "50.0%");
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
  assert.equal(fake.pills.get("a").label, "20.0%");

  // The older [A,B] reply lands last and must be discarded.
  stale.resolve(reply(0.8, 800, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "20.0%");
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
  assert.equal(fake.pills.get("a").label, "20.0%");

  first.resolve(reply(0.8, 800, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "20.0%");
});

test("a cumulative reply without a snapshot leaves the pill missing instead of borrowing another reading", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps);
  t.after(() => runtime.dispose());
  fake.enable();
  fake.emitSnapshot([agent("a")]);
  await advance(t, 10_000);
  // No cumulative snapshot. The reply does carry a completed turn (125 tokens
  // / 10 s), which the pill must not turn into a speed: it only shows the
  // cumulative cache rate.
  fake.pending.shift().resolve(reply(null, 125, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "—");
  assert.doesNotMatch(fake.pills.get("a").label, /t\/s|token|12\.5|最近|50/);
  assert.equal(fake.pills.get("a").title,
    "打开工作区用量 · 累计缓存 —（尚无有效累计快照）");
  // The agent still carries a valid recent `lastUsage` (50.0%) for the panel,
  // yet the empty cumulative slot stays empty instead of borrowing it.
  assert.doesNotMatch(fake.pills.get("a").title, /最近|50\.0%/);

  // A later cumulative reply is a valid reading and replaces the placeholder.
  fake.emitUpsert(agent("a", { updatedAt: "2026-11-22T00:00:00Z" }));
  await advance(t, 10_000);
  fake.pending.shift().resolve(reply(0.982, null, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "98.2%");
});

test("a closed cumulative setting keeps the pill missing and reads nothing", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps);
  t.after(() => runtime.dispose());
  fake.emitSnapshot([agent("a")]);
  assert.equal(fake.pills.get("a").label, "…");

  fake.enable({ enabled: false });
  const pill = fake.pills.get("a");
  assert.equal(pill.label, "—");
  assert.match(pill.title, /累计缓存 —（累计统计已关闭）/);
  await advance(t, 10_000);
  assert.equal(fake.calls.filter((call) => call.type === "rpc").length, 0);
});

test("a closed settings subscription is reopened and the pill recovers", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps);
  t.after(() => runtime.dispose());
  fake.enable();
  fake.emitSnapshot([agent("a")]);

  // The host rejects a replay while the plugin is still loading and never retries it.
  fake.closeSettings();
  assert.match(fake.pills.get("a").title, /累计设置错误：设置订阅已关闭/);
  await advance(t, 1_000);
  assert.deepEqual(fake.settings, { opened: 2, released: 1 });

  fake.enable();
  await advance(t, 10_000);
  fake.pending.shift().resolve(reply(0.5, null, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "50.0%");
});

test("settings retries back off to a capped delay, reset on success, and stop on dispose", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps);
  t.after(() => runtime.dispose());

  const expectReopenAfter = async (delay) => {
    const before = fake.settings.opened;
    fake.closeSettings();
    await advance(t, delay - 1);
    assert.equal(fake.settings.opened, before);
    await advance(t, 1);
    assert.equal(fake.settings.opened, before + 1);
  };
  for (const delay of [1_000, 2_000, 5_000, 10_000, 30_000, 30_000]) await expectReopenAfter(delay);
  fake.enable();
  await expectReopenAfter(1_000);

  const opened = fake.settings.opened;
  fake.closeSettings();
  runtime.dispose();
  await advance(t, 60_000);
  assert.equal(fake.settings.opened, opened);
});

test("a workspace outside the cumulative allowlist shows its own reason", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps);
  t.after(() => runtime.dispose());
  fake.enable({ workspaceIds: ["wks_elsewhere"] });
  fake.emitSnapshot([agent("a")]);
  const pill = fake.pills.get("a");
  assert.equal(pill.label, "—");
  assert.match(pill.title, /累计缓存 —（不在本机累计名单）/);
  await advance(t, 10_000);
  assert.equal(fake.calls.filter((call) => call.type === "rpc").length, 0);
});

test("a failed cumulative read is reported and never backfilled", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps);
  t.after(() => runtime.dispose());
  fake.enable();
  fake.emitSnapshot([agent("a")]);
  await advance(t, 10_000);
  fake.pending.shift().reject(new Error("rpc down"));
  await advance(t, 0);
  const pill = fake.pills.get("a");
  assert.equal(pill.label, "—");
  assert.match(pill.title, /累计缓存 —（累计读取失败/);
});

test("a real cumulative zero is a measurement, not a missing value", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps);
  t.after(() => runtime.dispose());
  fake.enable();
  fake.emitSnapshot([agent("a", { lastUsage: { inputTokens: 100, cachedInputTokens: 0 } })]);
  await advance(t, 10_000);
  fake.pending.shift().resolve(reply(0, 100, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "0.0%");
  assert.equal(fake.pills.get("a").title,
    "打开工作区用量 · 累计缓存 0.0%");
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
  assert.equal(fake.pills.get("a").label, "20.0%");
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
  assert.equal(fake.pills.get("a").label, "40.0%");

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
