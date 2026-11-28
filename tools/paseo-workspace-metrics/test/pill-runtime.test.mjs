import assert from "node:assert/strict";
import { test } from "node:test";
import { startPillRuntime } from "../client/pill-runtime.ts";
import { createCumulativeHub } from "../client/cumulative-hub.ts";

const WS = "wks_metrics";

function fakeClient() {
  const pills = new Map();
  const calls = [];
  let agentHandlers = null;
  let settingsHandlers = null;
  const pending = [];
  const scopeRequests = [];
  const settings = { opened: 0, released: 0 };
  return {
    settings,
    pills,
    calls,
    pending,
    scopeRequests,
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
      requestScope() {
        calls.push({ type: "scope" });
        return new Promise((resolve, reject) => scopeRequests.push({ resolve, reject }));
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
    resolveScope(patch = {}) {
      const request = scopeRequests.shift();
      return request.resolve({
        enabled: true,
        workspaceIds: [WS],
        allWorkspaces: false,
        codexHomeConfigured: true,
        error: null,
        ...patch,
      });
    },
    failScope() {
      scopeRequests.shift().reject(new Error("scope rpc down"));
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

/**
 * Startup scope read that answers on its own, like a healthy backend: no test
 * step is needed to get past it, so the pill alone has to move the label.
 */
function autoScopeClient() {
  const fake = fakeClient();
  fake.deps.requestScope = () => Promise.resolve({
    enabled: true,
    workspaceIds: [WS],
    allWorkspaces: false,
    codexHomeConfigured: true,
    error: null,
  });
  return fake;
}

async function advance(t, ms) {
  t.mock.timers.tick(ms);
  await settle();
}

test("a terminal transition re-reads after the rollout flush without new directory events", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps, createCumulativeHub());
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

test("an earlier valid reply still reaches the label when a follow-up was demanded", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps, createCumulativeHub());
  t.after(() => runtime.dispose());
  fake.enable();
  fake.emitSnapshot([agent("a", { status: "running" })]);
  await advance(t, 10_000);
  const first = fake.pending.shift();

  // The turn ends before the first read returns; the terminal transition asks
  // for a bounded follow-up. It waits for the read already in flight.
  fake.emitUpsert(agent("a", { status: "idle" }));
  await advance(t, 1_200);
  assert.equal(fake.pending.length, 0, "overlapping reads for one workspace are serialized");

  // The first read lands with a valid 96.2% while nothing newer is shown.
  first.resolve(reply(0.962, 962, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "96.2%");
  assert.equal(fake.pills.get("a").title, "打开工作区用量 · 累计缓存 96.2%");

  // The coalesced follow-up then starts by itself and can still refresh it.
  assert.equal(fake.pending.length, 1);
  assert.equal(fake.pending[0].input.refresh, true);
  fake.pending.shift().resolve(reply(0.971, 971, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "97.1%");
});

test("a second terminal turn during the chain restores the budget for its rollout", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps, createCumulativeHub());
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
  const runtime = startPillRuntime(fake.deps, createCumulativeHub());
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
  // The stale [A,B] success is voided; the last valid reading stays on the
  // still-visible workspace while the chain reads the current members.
  assert.equal(fake.pills.get("a").label, "25.0%");

  await advance(t, 1_200);
  assert.equal(fake.pending.length, 1);
  assert.deepEqual(fake.pending[0].input, { workspaceId: WS, agentIds: ["a"], refresh: true });
  fake.pending.shift().resolve(reply(0.2, 200, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "20.0%");
});

test("a member change keeps the last reading until its matching reply lands", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps, createCumulativeHub());
  t.after(() => runtime.dispose());
  fake.enable();
  fake.emitSnapshot([agent("a"), agent("b")]);
  await advance(t, 10_000);
  fake.pending.shift().resolve(reply(0.4, 400, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "40.0%");

  // A third conversation appears: every pill for the same workspace keeps
  // showing 40.0% while the member-triggered re-read is still pending.
  fake.emitUpsert(agent("c"));
  for (const id of ["a", "b", "c"]) assert.equal(fake.pills.get(id).label, "40.0%");
  assert.equal(fake.pending.length, 0, "the routine window defers the read");

  await advance(t, 10_000);
  const superseded = fake.pending.shift();
  assert.deepEqual(superseded.input.agentIds, ["a", "b", "c"]);
  assert.equal(fake.pills.get("c").label, "40.0%");

  // A newer member change voids that read; its late reply must not land.
  fake.emitUpsert(agent("d"));
  superseded.resolve(reply(0.8, 800, 10_000));
  await advance(t, 0);
  for (const id of ["a", "b", "c", "d"]) assert.equal(fake.pills.get(id).label, "40.0%");

  await advance(t, 10_000);
  const fresh = fake.pending.shift();
  assert.deepEqual(fresh.input.agentIds, ["a", "b", "c", "d"]);
  fresh.resolve(reply(0.7, 700, 10_000));
  await advance(t, 0);
  for (const id of ["a", "b", "c", "d"]) assert.equal(fake.pills.get(id).label, "70.0%");
});

test("a member change retains a real zero until the new reading replaces it", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps, createCumulativeHub());
  t.after(() => runtime.dispose());
  fake.enable();
  fake.emitSnapshot([agent("a")]);
  await advance(t, 10_000);
  fake.pending.shift().resolve(reply(0, 0, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "0.0%");

  fake.emitUpsert(agent("b"));
  assert.equal(fake.pills.get("a").label, "0.0%");
  assert.equal(fake.pills.get("b").label, "0.0%");

  await advance(t, 10_000);
  fake.pending.shift().resolve(reply(0.6, 600, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "60.0%");
  assert.equal(fake.pills.get("b").label, "60.0%");
});

test("a member-driven re-read replaces the retained reading even without a valid snapshot", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps, createCumulativeHub());
  t.after(() => runtime.dispose());
  fake.enable();
  fake.emitSnapshot([agent("a")]);
  await advance(t, 10_000);
  fake.pending.shift().resolve(reply(0.4, 400, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "40.0%");

  fake.emitUpsert(agent("b"));
  assert.equal(fake.pills.get("a").label, "40.0%");
  await advance(t, 10_000);
  fake.pending.shift().resolve(reply(null, null, 10_000));
  await advance(t, 0);
  // A finished read without a valid snapshot keeps its own missing meaning
  // instead of letting the retained 40.0% linger.
  assert.equal(fake.pills.get("a").label, "—");
  assert.equal(fake.pills.get("a").title,
    "打开工作区用量 · 累计缓存 —（尚无有效累计快照）");

  // Only a valid rate is kept: an empty or failed reading is cleared by the
  // member change and the pill goes back to its loading label.
  fake.emitUpsert(agent("c"));
  assert.equal(fake.pills.get("a").label, "…");
  await advance(t, 10_000);
  fake.pending.shift().reject(new Error("rpc down"));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "—");
  assert.match(fake.pills.get("a").title, /累计读取失败/);

  fake.emitUpsert(agent("d"));
  assert.equal(fake.pills.get("a").label, "…");
});

test("a settings update still clears the reading kept across a member change", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps, createCumulativeHub());
  t.after(() => runtime.dispose());
  fake.enable();
  fake.emitSnapshot([agent("a")]);
  await advance(t, 10_000);
  fake.pending.shift().resolve(reply(0.4, 400, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "40.0%");

  // Only a member change keeps the reading; a settings generation change is
  // a different scope and must not carry it over.
  fake.enable();
  assert.equal(fake.pills.get("a").label, "…");
  assert.equal(fake.pills.get("a").title, "打开工作区用量 · 累计缓存 …");
  await advance(t, 10_000);
  fake.pending.shift().resolve(reply(0.6, 600, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "60.0%");
});

test("a workspace that loses every visible member drops the retained reading", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps, createCumulativeHub());
  t.after(() => runtime.dispose());
  fake.enable();
  fake.emitSnapshot([agent("a")]);
  await advance(t, 10_000);
  fake.pending.shift().resolve(reply(0.4, 400, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "40.0%");

  fake.emitRemove("a");
  assert.equal(fake.pills.size, 0);

  // Back in the same workspace the first read is a fresh load, not the old
  // reading of a workspace nobody could see.
  fake.emitSnapshot([agent("a")]);
  assert.equal(fake.pills.get("a").label, "…");
  await advance(t, 10_000);
  fake.pending.shift().resolve(reply(0.6, 600, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "60.0%");
});

test("follow-up reads are bounded and stop", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps, createCumulativeHub());
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
  const runtime = startPillRuntime(fake.deps, createCumulativeHub());
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
  const runtime = startPillRuntime(fake.deps, createCumulativeHub());
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

test("a reply for an archived member set cannot overwrite the current workspace", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps, createCumulativeHub());
  t.after(() => runtime.dispose());
  fake.enable();
  fake.emitSnapshot([agent("a", { status: "running" }), agent("b")]);
  await advance(t, 10_000);
  const stale = fake.pending.shift();
  assert.deepEqual(stale.input.agentIds, ["a", "b"]);

  // B is archived while [A,B] is still in flight.
  fake.emitUpsert(agent("b", { archivedAt: "2026-11-22T00:00:00Z" }));
  assert.equal(fake.pills.has("b"), false);

  // The in-flight read still owns the workspace, so the member-triggered read
  // waits for it instead of opening a second overlapping request.
  await advance(t, 10_000);
  assert.equal(fake.pending.length, 0);
  stale.resolve(reply(0.8, 800, 10_000));
  await advance(t, 0);
  // That reply belongs to the old member set; it must not land.
  assert.equal(fake.pills.get("a").label, "…");

  await advance(t, 0);
  const fresh = fake.pending.shift();
  assert.deepEqual(fresh.input.agentIds, ["a"]);
  fresh.resolve(reply(0.2, 200, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "20.0%");
});

test("a cumulative reply without a snapshot leaves the pill missing instead of borrowing another reading", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps, createCumulativeHub());
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
  const runtime = startPillRuntime(fake.deps, createCumulativeHub());
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
  const runtime = startPillRuntime(fake.deps, createCumulativeHub());
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
  const runtime = startPillRuntime(fake.deps, createCumulativeHub());
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
  const runtime = startPillRuntime(fake.deps, createCumulativeHub());
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
  const runtime = startPillRuntime(fake.deps, createCumulativeHub());
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
  const runtime = startPillRuntime(fake.deps, createCumulativeHub());
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

test("failures from a reply that no longer matches the members are ignored", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps, createCumulativeHub());
  t.after(() => runtime.dispose());
  fake.enable();
  fake.emitSnapshot([agent("a"), agent("b")]);
  await advance(t, 10_000);
  const stale = fake.pending.shift();
  fake.emitRemove("b");
  await advance(t, 10_000);
  stale.reject(new Error("late failure"));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "…", "the old member set's failure cannot land");

  const fresh = fake.pending.shift();
  assert.deepEqual(fresh.input.agentIds, ["a"]);
  fresh.resolve(reply(0.2, 200, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "20.0%");
});

test("workspace migration and background flag recompute membership", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps, createCumulativeHub());
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
  const runtime = startPillRuntime(fake.deps, createCumulativeHub());
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

test("a fresh client reaches its cumulative label with no settings event and no user action", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = autoScopeClient();
  const runtime = startPillRuntime(fake.deps, createCumulativeHub());
  t.after(() => runtime.dispose());

  // Fresh open: the directory arrives, the settings stream stays silent. Before
  // the startup read existed nothing ever resolved the scope, so the pill sat
  // on "…" and issued no cumulative request until the panel was opened.
  fake.emitSnapshot([agent("a", { status: "idle" })]);
  assert.equal(fake.pills.get("a").label, "…");
  await settle();
  await advance(t, 10_000);
  assert.equal(fake.pending.length, 1, "the pill read starts on its own");
  fake.pending.shift().resolve(reply(0.962, null, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "96.2%");
  assert.equal(fake.pills.get("a").title, "打开工作区用量 · 累计缓存 96.2%");
});

test("the startup scope read fills the pill when the settings stream never delivers", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps, createCumulativeHub());
  t.after(() => runtime.dispose());

  // The directory arrives, then the settings stream stays silent: no first
  // event, exactly the fresh-open case where scope used to stay null forever.
  fake.emitSnapshot([agent("a", { status: "idle" })]);
  assert.equal(fake.pills.get("a").label, "…");
  assert.deepEqual(fake.scopeRequests.length, 1, "one direct scope read at startup");
  assert.equal(fake.calls.filter((call) => call.type === "rpc").length, 0);

  fake.resolveScope();
  await settle();
  await advance(t, 0);
  assert.equal(fake.scopeRequests.length, 0);
  // The resolved scope lets the routine read start without any user action.
  await advance(t, 10_000);
  assert.deepEqual(fake.pending.map((entry) => entry.input), [{ workspaceId: WS, agentIds: ["a"], refresh: false }]);
  fake.pending.shift().resolve(reply(0.962, null, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "96.2%");
  assert.equal(fake.pills.get("a").title, "打开工作区用量 · 累计缓存 96.2%");
});

test("a startup scope reply arriving after the settings event cannot replace it", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps, createCumulativeHub());
  t.after(() => runtime.dispose());
  fake.emitSnapshot([agent("a")]);

  // The settings stream wins first, excluding this workspace.
  fake.enable({ workspaceIds: ["wks_elsewhere"] });
  assert.match(fake.pills.get("a").title, /不在本机累计名单/);

  // The older direct read then answers with an all-workspaces scope; it must
  // not resurrect the workspace or clear the settings error.
  fake.resolveScope({ allWorkspaces: true, workspaceIds: [] });
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "—");
  assert.match(fake.pills.get("a").title, /不在本机累计名单/);
  await advance(t, 10_000);
  assert.equal(fake.calls.filter((call) => call.type === "rpc").length, 0);
});

test("a startup scope reply arriving after a close cannot revive the pill", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps, createCumulativeHub());
  t.after(() => runtime.dispose());
  fake.emitSnapshot([agent("a")]);

  fake.closeSettings();
  assert.match(fake.pills.get("a").title, /累计设置错误：设置订阅已关闭/);
  fake.resolveScope();
  await advance(t, 0);
  assert.match(fake.pills.get("a").title, /累计设置错误：设置订阅已关闭/);
  assert.equal(fake.calls.filter((call) => call.type === "rpc").length, 0);
});

test("a startup scope reply arriving after dispose is ignored", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps, createCumulativeHub());
  fake.emitSnapshot([agent("a")]);
  runtime.dispose();

  fake.resolveScope();
  await advance(t, 20_000);
  assert.equal(fake.pills.size, 0);
  assert.equal(fake.calls.filter((call) => call.type === "rpc").length, 0);
});

test("the startup scope read keeps a reading the panel already published", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const hub = createCumulativeHub();
  const runtime = startPillRuntime(fake.deps, hub);
  t.after(() => runtime.dispose());
  fake.emitSnapshot([agent("a")]);
  hub.publish(WS, hub.begin(WS), { rate: 0.962, error: null });
  assert.equal(fake.pills.get("a").label, "96.2%");

  // The direct read confirms the scope; the panel's backend-validated reading
  // stays on the label and is not immediately re-read against the short cache.
  fake.resolveScope();
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "96.2%");
  assert.equal(hub.read(WS).rate, 0.962);
  assert.equal(fake.calls.filter((call) => call.type === "rpc").length, 0);
  await advance(t, 10_000);
  assert.equal(fake.calls.filter((call) => call.type === "rpc" && !call.refresh).length, 1);
});

test("a failed startup scope read leaves the settings stream as the only source", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps, createCumulativeHub());
  t.after(() => runtime.dispose());
  fake.failScope();
  await advance(t, 10_000);
  assert.equal(fake.pills.size, 0);
  assert.equal(fake.calls.filter((call) => call.type === "rpc").length, 0);

  // A later settings event still works.
  fake.enable();
  fake.emitSnapshot([agent("a")]);
  await advance(t, 10_000);
  fake.pending.shift().resolve(reply(0.4, null, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "40.0%");
});

test("the startup scope read reports a disabled or out-of-allowlist setting", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps, createCumulativeHub());
  t.after(() => runtime.dispose());
  fake.emitSnapshot([agent("a")]);
  fake.resolveScope({ enabled: false, workspaceIds: [] });
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "—");
  assert.match(fake.pills.get("a").title, /累计统计已关闭/);
  await advance(t, 10_000);
  assert.equal(fake.calls.filter((call) => call.type === "rpc").length, 0);
});

test("a later settings event still owns the scope after the startup read", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps, createCumulativeHub());
  t.after(() => runtime.dispose());
  fake.emitSnapshot([agent("a")]);
  fake.resolveScope();
  // The reply adopts scope in a microtask; its routine timer starts after that.
  await settle();
  await advance(t, 10_000);
  assert.equal(fake.pending.length, 1);
  fake.pending.shift().resolve(reply(0.3, null, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "30.0%");

  // The real settings stream then changes the allowlist away from this
  // workspace. Its generation clears the accumulated reading as before.
  fake.enable({ workspaceIds: ["wks_elsewhere"] });
  assert.equal(fake.pills.get("a").label, "—");
  assert.match(fake.pills.get("a").title, /不在本机累计名单/);
});

test("a pill surface's own scope read feeds the one runtime and starts its read", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  // The runtime's own startup read and settings stream both stay silent, as on
  // the cold start where only the composer pill is mounted.
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps, createCumulativeHub());
  t.after(() => runtime.dispose());
  fake.emitSnapshot([agent("a")]);
  assert.equal(fake.pills.get("a").label, "…");
  assert.equal(fake.calls.filter((call) => call.type === "rpc").length, 0);

  assert.equal(runtime.adoptScope({
    enabled: true, workspaceIds: [WS], allWorkspaces: false,
    codexHomeConfigured: true, error: null,
  }), true, "the first resolution is adopted");
  await advance(t, 10_000);
  assert.deepEqual(fake.pending.map((entry) => entry.input),
    [{ workspaceId: WS, agentIds: ["a"], refresh: false }]);
  fake.pending.shift().resolve(reply(0.976, null, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "97.6%");
});

test("a second surface scope cannot displace the adopted one, a later settings event still owns changes", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps, createCumulativeHub());
  t.after(() => runtime.dispose());
  fake.emitSnapshot([agent("a")]);
  assert.equal(runtime.adoptScope({
    enabled: true, workspaceIds: [WS], allWorkspaces: false,
    codexHomeConfigured: true, error: null,
  }), true);
  // Another pill mounting does not clear and re-read.
  assert.equal(runtime.adoptScope({
    enabled: true, workspaceIds: ["wks_elsewhere"], allWorkspaces: false,
    codexHomeConfigured: true, error: null,
  }), false);
  fake.enable({ workspaceIds: ["wks_elsewhere"] });
  assert.equal(fake.pills.get("a").label, "—", "the settings stream still owns later changes");
  assert.match(fake.pills.get("a").title, /不在本机累计名单/);
});

test("an adopted disabled or out-of-scope setting reads no cumulative data", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const disabled = fakeClient();
  const off = startPillRuntime(disabled.deps, createCumulativeHub());
  t.after(() => off.dispose());
  disabled.emitSnapshot([agent("a")]);
  off.adoptScope({
    enabled: false, workspaceIds: [], allWorkspaces: false,
    codexHomeConfigured: true, error: null,
  });
  await advance(t, 60_000);
  assert.equal(disabled.calls.filter((call) => call.type === "rpc").length, 0);
  assert.equal(disabled.pills.get("a").label, "—");

  const outside = fakeClient();
  const scoped = startPillRuntime(outside.deps, createCumulativeHub());
  t.after(() => scoped.dispose());
  outside.emitSnapshot([agent("a")]);
  scoped.adoptScope({
    enabled: true, workspaceIds: ["wks_elsewhere"], allWorkspaces: false,
    codexHomeConfigured: true, error: null,
  });
  await advance(t, 60_000);
  assert.equal(outside.calls.filter((call) => call.type === "rpc").length, 0);
});

test("after an adopted scope, a member change voids the older reply and reads all members", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps, createCumulativeHub());
  t.after(() => runtime.dispose());
  fake.emitSnapshot([agent("a")]);
  runtime.adoptScope({
    enabled: true, workspaceIds: [WS], allWorkspaces: false,
    codexHomeConfigured: true, error: null,
  });
  await advance(t, 10_000);
  const stale = fake.pending.shift();
  assert.deepEqual(stale.input.agentIds, ["a"]);

  fake.emitUpsert(agent("b"));
  await advance(t, 10_000);
  stale.resolve(reply(0.1, 100, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "…", "the older member set's reply cannot land");

  const fresh = fake.pending.shift();
  assert.deepEqual(fresh.input.agentIds, ["a", "b"]);
  fresh.resolve(reply(0.7, 700, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "70.0%");
});

test("an adopted scope is ignored after dispose", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps, createCumulativeHub());
  runtime.dispose();
  assert.equal(runtime.adoptScope({
    enabled: true, workspaceIds: [WS], allWorkspaces: false,
    codexHomeConfigured: true, error: null,
  }), false);
});

test("a late surface scope keeps the reading the panel already published", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const hub = createCumulativeHub();
  const runtime = startPillRuntime(fake.deps, hub);
  t.after(() => runtime.dispose());
  fake.emitSnapshot([agent("a")]);
  assert.equal(fake.pills.get("a").label, "…");

  // The user opens the popover first: the panel's own read publishes 97.6%.
  hub.publish(WS, hub.begin(WS), { rate: 0.976, error: null });
  assert.equal(fake.pills.get("a").label, "97.6%");

  // The pill surface's scope read lands later. It must not clear that reading.
  assert.equal(runtime.adoptScope({
    enabled: true, workspaceIds: [WS], allWorkspaces: false,
    codexHomeConfigured: true, error: null,
  }), true);
  assert.equal(fake.pills.get("a").label, "97.6%");
  assert.deepEqual(hub.read(WS), { rate: 0.976, error: null });

  // Its routine read still starts from the current members and replaces it.
  await advance(t, 10_000);
  assert.deepEqual(fake.pending.map((entry) => entry.input),
    [{ workspaceId: WS, agentIds: ["a"], refresh: false }]);
  fake.pending.shift().resolve(reply(0.962, null, 10_000));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "96.2%");
});
