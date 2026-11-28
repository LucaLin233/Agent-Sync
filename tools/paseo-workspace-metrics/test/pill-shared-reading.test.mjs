import assert from "node:assert/strict";
import { test } from "node:test";
import { startPillRuntime } from "../client/pill-runtime.ts";
import { createCumulativeHub } from "../client/cumulative-hub.ts";

const WS = "wks_shared";

function fakeClient() {
  const pills = new Map();
  let agentHandlers = null;
  let settingsHandlers = null;
  return {
    pills,
    deps: {
      addPill({ workspaceId, agentId, title, label }) {
        const pill = { workspaceId, agentId, title, label };
        pills.set(agentId, pill);
        return {
          update(patch) {
            if (patch.title !== undefined) pill.title = patch.title;
            if (patch.label !== undefined) pill.label = patch.label;
          },
          remove() { pills.delete(agentId); },
        };
      },
      openPanel() {},
      requestCumulative: () => new Promise(() => {}),
      subscribeAgents(handlers) {
        agentHandlers = handlers;
        return () => { agentHandlers = null; };
      },
      subscribeSettings(handlers) {
        settingsHandlers = handlers;
        return () => { settingsHandlers = null; };
      },
    },
    emitSnapshot(entries) { agentHandlers.snapshot(entries); },
    emitUpsert(agent) {
      agentHandlers.update({ type: "agent_update", payload: { kind: "upsert", agent } });
    },
    enable(patch = {}) {
      settingsHandlers.next({
        enabled: true, workspaceIds: [WS], allWorkspaces: false,
        codexHomeConfigured: true, error: null, ...patch,
      });
    },
  };
}

const agent = (id) => ({ id, workspaceId: WS, provider: "codex", status: "idle" });

test("a reading the panel publishes reaches the button and its title", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const hub = createCumulativeHub();
  const runtime = startPillRuntime(fake.deps, hub);
  t.after(() => runtime.dispose());
  fake.enable();
  fake.emitSnapshot([agent("a"), agent("b")]);
  assert.equal(fake.pills.get("a").label, "…");

  // The panel runs its own cumulative query and publishes the result; no pill
  // read has returned yet.
  hub.publish(WS, hub.begin(WS), { rate: 0.962, error: null });
  for (const id of ["a", "b"]) {
    assert.equal(fake.pills.get(id).label, "96.2%");
    assert.equal(fake.pills.get(id).title, "打开工作区用量 · 累计缓存 96.2%");
  }
});

test("a panel reading of a real zero also replaces the loading label", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const hub = createCumulativeHub();
  const runtime = startPillRuntime(fake.deps, hub);
  t.after(() => runtime.dispose());
  fake.enable();
  fake.emitSnapshot([agent("a")]);
  hub.publish(WS, hub.begin(WS), { rate: 0, error: null });
  assert.equal(fake.pills.get("a").label, "0.0%");
  assert.equal(fake.pills.get("a").title, "打开工作区用量 · 累计缓存 0.0%");
});

test("another workspace's panel reading never moves this workspace's button", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const hub = createCumulativeHub();
  const runtime = startPillRuntime(fake.deps, hub);
  t.after(() => runtime.dispose());
  fake.enable({ allWorkspaces: true, workspaceIds: [] });
  fake.emitSnapshot([agent("a"), { ...agent("b"), workspaceId: "wks_other" }]);
  hub.publish("wks_other", hub.begin("wks_other"), { rate: 0.5, error: null });
  assert.equal(fake.pills.get("a").label, "…");
  assert.equal(fake.pills.get("b").label, "50.0%");
});

test("a settings change drops a reading obtained by either surface", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const hub = createCumulativeHub();
  const runtime = startPillRuntime(fake.deps, hub);
  t.after(() => runtime.dispose());
  fake.enable();
  fake.emitSnapshot([agent("a")]);
  hub.publish(WS, hub.begin(WS), { rate: 0.962, error: null });
  assert.equal(fake.pills.get("a").label, "96.2%");
  fake.enable();
  assert.equal(fake.pills.get("a").label, "…");
  assert.equal(hub.read(WS), undefined);
});

test("a panel reading fills the button while the pill's own first read is in flight", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const hub = createCumulativeHub();
  const runtime = startPillRuntime(fake.deps, hub);
  t.after(() => runtime.dispose());
  fake.enable();
  fake.emitSnapshot([agent("a")]);
  assert.equal(fake.pills.get("a").label, "…");

  // The pill's read started first; the panel's query started later and finished
  // first with the valid reading.
  const pillTicket = hub.begin(WS);
  hub.publish(WS, hub.begin(WS), { rate: 0.962, error: null });
  assert.equal(fake.pills.get("a").label, "96.2%");

  // The pill's older reply arriving now cannot replace the newer panel reading.
  assert.equal(hub.publish(WS, pillTicket, { rate: 0.801, error: null }), false);
  assert.equal(fake.pills.get("a").label, "96.2%");
  assert.equal(fake.pills.get("a").title, "打开工作区用量 · 累计缓存 96.2%");
});

test("a reading the panel validated fills the button before this client's settings arrive", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const hub = createCumulativeHub();
  const runtime = startPillRuntime(fake.deps, hub);
  t.after(() => runtime.dispose());
  // The agent directory is here, but this client's settings stream has not
  // delivered its first event yet: scope is still unknown, not "disabled".
  fake.emitSnapshot([agent("a"), agent("b")]);
  assert.equal(fake.pills.get("a").label, "…");

  // The panel's own settings stream already completed a real cumulative read
  // for this workspace and published the backend-validated 96.2%.
  hub.publish(WS, hub.begin(WS), { rate: 0.962, error: null });
  for (const id of ["a", "b"]) {
    assert.equal(fake.pills.get(id).label, "96.2%");
    assert.equal(fake.pills.get(id).title, "打开工作区用量 · 累计缓存 96.2%");
  }
});

test("an unknown scope keeps a shared reading across later directory updates", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const hub = createCumulativeHub();
  const runtime = startPillRuntime(fake.deps, hub);
  t.after(() => runtime.dispose());
  fake.emitSnapshot([agent("a")]);
  hub.publish(WS, hub.begin(WS), { rate: 0, error: null });

  // A directory update before the settings event must not wipe the reading the
  // panel already validated; a real zero included.
  fake.emitUpsert(agent("b"));
  assert.equal(fake.pills.get("a").label, "0.0%");
  assert.equal(fake.pills.get("b").label, "0.0%");
});

test("the first settings event still clears a reading shown while scope was unknown", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const hub = createCumulativeHub();
  const runtime = startPillRuntime(fake.deps, hub);
  t.after(() => runtime.dispose());
  fake.emitSnapshot([agent("a")]);
  hub.publish(WS, hub.begin(WS), { rate: 0.962, error: null });
  assert.equal(fake.pills.get("a").label, "96.2%");

  // The setting is explicit now. Its generation owns the reading from here.
  fake.enable();
  assert.equal(fake.pills.get("a").label, "…");
  assert.equal(hub.read(WS), undefined);
});

test("an explicit disabled setting hides a shared reading even if one arrives", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const hub = createCumulativeHub();
  const runtime = startPillRuntime(fake.deps, hub);
  t.after(() => runtime.dispose());
  fake.enable({ enabled: false });
  fake.emitSnapshot([agent("a")]);
  hub.publish(WS, hub.begin(WS), { rate: 0.962, error: null });
  assert.equal(fake.pills.get("a").label, "—");
  assert.equal(fake.pills.get("a").title, "打开工作区用量 · 累计缓存 —（累计统计已关闭）");
});

test("an allowlist that excludes the workspace hides a shared reading too", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const hub = createCumulativeHub();
  const runtime = startPillRuntime(fake.deps, hub);
  t.after(() => runtime.dispose());
  fake.enable({ workspaceIds: ["wks_elsewhere"] });
  fake.emitSnapshot([agent("a")]);
  hub.publish(WS, hub.begin(WS), { rate: 0.962, error: null });
  assert.equal(fake.pills.get("a").label, "—");
  assert.equal(fake.pills.get("a").title, "打开工作区用量 · 累计缓存 —（不在本机累计名单）");
});

test("a newer panel reading still replaces one the pill already showed", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const pending = [];
  fake.deps.requestCumulative = (input) => new Promise((resolve, reject) => pending.push({ input, resolve, reject }));
  const hub = createCumulativeHub();
  const runtime = startPillRuntime(fake.deps, hub);
  t.after(() => runtime.dispose());
  fake.enable();
  fake.emitSnapshot([agent("a")]);

  // The pill's own read is request A and lands first.
  t.mock.timers.tick(10_000);
  for (let i = 0; i < 6; i += 1) await Promise.resolve();
  const first = pending.shift();
  assert.ok(first, "the pill issued its own read");
  first.resolve({ rate: 0.962, error: null });
  for (let i = 0; i < 6; i += 1) await Promise.resolve();
  assert.equal(fake.pills.get("a").label, "96.2%");

  // Another request that started before the panel's yet-unanswered one.
  const older = hub.begin(WS);
  // A later panel query (request B) finishes and must still win.
  const newer = hub.begin(WS);
  assert.equal(hub.publish(WS, newer, { rate: 0.971, error: null }), true);
  assert.equal(fake.pills.get("a").label, "97.1%");
  assert.equal(fake.pills.get("a").title, "打开工作区用量 · 累计缓存 97.1%");
  // And the older request cannot come back and undo it.
  assert.equal(hub.publish(WS, older, { rate: 0.5, error: null }), false);
  assert.equal(fake.pills.get("a").label, "97.1%");
});

test("the first directory snapshot keeps a reading the panel published earlier", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const hub = createCumulativeHub();
  const runtime = startPillRuntime(fake.deps, hub);
  t.after(() => runtime.dispose());
  // The panel finishes before the pill has seen the agent directory at all.
  hub.publish(WS, hub.begin(WS), { rate: 0.962, error: null });
  fake.emitSnapshot([agent("a")]);
  assert.equal(fake.pills.get("a").label, "96.2%");
  assert.equal(fake.pills.get("a").title, "打开工作区用量 · 累计缓存 96.2%");
});


test("the first directory snapshot does not void a panel read already in flight", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const hub = createCumulativeHub();
  const runtime = startPillRuntime(fake.deps, hub);
  t.after(() => runtime.dispose());
  // The panel's query starts for this workspace, then the directory snapshot
  // reveals its members for the first time.
  const panel = hub.begin(WS);
  fake.emitSnapshot([agent("a")]);
  assert.equal(fake.pills.get("a").label, "…");
  assert.equal(hub.publish(WS, panel, { rate: 0.962, error: null }), true);
  assert.equal(fake.pills.get("a").label, "96.2%");
  assert.equal(fake.pills.get("a").title, "打开工作区用量 · 累计缓存 96.2%");
});

test("a real member change still voids an in-flight panel read", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const hub = createCumulativeHub();
  const runtime = startPillRuntime(fake.deps, hub);
  t.after(() => runtime.dispose());
  fake.enable();
  fake.emitSnapshot([agent("a")]);
  const panel = hub.begin(WS);
  hub.publish(WS, hub.begin(WS), { rate: 0.962, error: null });
  assert.equal(fake.pills.get("a").label, "96.2%");

  // A second visible member joins: the old reply belongs to the previous set.
  fake.emitUpsert(agent("b"));
  assert.equal(hub.publish(WS, panel, { rate: 0.5, error: null }), false);
  assert.equal(fake.pills.get("a").label, "96.2%");
});
