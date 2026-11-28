import assert from "node:assert/strict";
import { test } from "node:test";
import { startPillRuntime } from "../client/pill-runtime.ts";
import { createCumulativeHub } from "../client/cumulative-hub.ts";
import { createSharedStore } from "../client/shared-store.ts";

const WS = "wks_shared_query";
const scope = (patch = {}) => ({
  enabled: true, workspaceIds: [WS], allWorkspaces: false,
  codexHomeConfigured: true, error: null, ...patch,
});

function fakeClient() {
  const pills = new Map();
  const calls = [];
  const pending = [];
  let agentHandlers = null;
  let settingsHandlers = null;
  return {
    pills,
    calls,
    pending,
    deps: {
      addPill({ workspaceId, agentId, title, label, onPress }) {
        pills.set(agentId, { workspaceId, agentId, title, label, onPress });
        return {
          update(patch) {
            const pill = pills.get(agentId);
            if (!pill) return;
            if (patch.title !== undefined) pill.title = patch.title;
            if (patch.label !== undefined) pill.label = patch.label;
          },
          remove() { pills.delete(agentId); },
        };
      },
      openPanel() {},
      requestCumulative(input) {
        calls.push({ type: "rpc", ...input });
        return new Promise((resolve, reject) => pending.push({ input, resolve, reject }));
      },
      requestScope: () => new Promise(() => {}),
      subscribeAgents(handlers) {
        agentHandlers = handlers;
        return () => { agentHandlers = null; };
      },
      subscribeSettings(handlers) {
        settingsHandlers = handlers;
        return () => { settingsHandlers = null; };
      },
    },
    directory(entries) { agentHandlers.snapshot(entries); },
    settings: (event) => settingsHandlers.next(event),
    closeSettings: () => settingsHandlers.closed(),
  };
}

const agent = (id, patch = {}) => ({ id, workspaceId: WS, provider: "codex", status: "idle", ...patch });
const reply = (rate) => ({
  workspaceId: WS, inputTokens: 100, cachedInputTokens: 50, covered: 1, eligible: 1,
  missing: 0, unavailable: 0, rate, error: null, latestSamples: [], recentTurn: null,
  turns: { sessions: 1, completed: 1, speedSamples: 1, firstTokenSamples: 0,
    outputTokens: 0, elapsedMs: 0, firstTokenTotalMs: 0 },
});

const advance = async (t, ms) => {
  t.mock.timers.tick(ms);
  await Promise.resolve();
  await new Promise((resolve) => setImmediate(resolve));
};

test("while a pill surface owns the read, routine and member demands issue no second RPC", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const hub = createCumulativeHub();
  const shared = createSharedStore();
  const runtime = startPillRuntime(fake.deps, hub, shared);
  t.after(() => runtime.dispose());

  fake.settings(scope());
  fake.directory([agent("a")]);
  const release = shared.claimSurface(WS);
  t.after(release);

  // The mounted pill queries under its own key; the runtime must not race it.
  await advance(t, 60_000);
  assert.equal(fake.calls.length, 0, "no timer-driven RPC while the surface owns the read");

  // A member change is carried by the surface's own key, not a runtime read.
  fake.directory([agent("a"), agent("b")]);
  await advance(t, 60_000);
  assert.equal(fake.calls.length, 0);
});

test("a terminal follow-up asks both surfaces for one fresh revision instead of a side RPC", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const hub = createCumulativeHub();
  const shared = createSharedStore();
  const runtime = startPillRuntime(fake.deps, hub, shared);
  t.after(() => runtime.dispose());
  fake.settings(scope());
  fake.directory([agent("a", { status: "running" })]);
  const release = shared.claimSurface(WS);
  t.after(release);

  const before = shared.workspaceRevision(WS);
  fake.directory([agent("a", { status: "idle", updatedAt: "2026-11-28T00:00:00Z" })]);
  await advance(t, 2_000);
  assert.equal(shared.workspaceRevision(WS), before + 1, "one bump drives this workspace's shared key");
  assert.equal(shared.refreshIntent(WS, shared.workspaceRevision(WS)), true,
    "a terminal read bypasses the short cache");
  assert.equal(shared.refreshIntent(WS, before), false, "an earlier revision does not inherit it");
  assert.equal(fake.calls.length, 0);
});

test("after the last pill releases, the runtime reads again with its own single flight", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const shared = createSharedStore();
  const runtime = startPillRuntime(fake.deps, createCumulativeHub(), shared);
  t.after(() => runtime.dispose());
  fake.settings(scope());
  fake.directory([agent("a")]);
  const release = shared.claimSurface(WS);
  release();

  // With no surface left, the runtime's own routine read resumes on its
  // existing interval and feeds the label.
  await advance(t, 10_000);
  assert.deepEqual(fake.calls.map(({ type, ...input }) => input),
    [{ workspaceId: WS, agentIds: ["a"], refresh: false }]);
  fake.pending.shift().resolve(reply(0.976));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "97.6%");
});

test("a shared settings change gates the surface read immediately", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const shared = createSharedStore();
  const runtime = startPillRuntime(fake.deps, createCumulativeHub(), shared);
  t.after(() => runtime.dispose());
  fake.directory([agent("a")]);

  // The runtime's settings stream publishes the scope into the shared store.
  fake.settings(scope());
  assert.equal(shared.scope()?.enabled, true);

  // Turning the feature off updates the same store, so a mounted surface stops.
  fake.settings(scope({ enabled: false }));
  assert.equal(shared.scope()?.enabled, false);
  await advance(t, 60_000);
  assert.equal(fake.calls.length, 0);
  assert.equal(fake.pills.get("a").label, "—");
});

test("a closed settings stream is published as a real failure, so the surface stops reading", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const shared = createSharedStore();
  const runtime = startPillRuntime(fake.deps, createCumulativeHub(), shared);
  t.after(() => runtime.dispose());
  fake.directory([agent("a")]);
  fake.settings(scope());
  assert.equal(shared.scopeStatus(), "live");

  fake.closeSettings();
  assert.equal(shared.scopeStatus(), "failed", "a closed stream is not pending forever");
  assert.equal(shared.scope()?.enabled, false);
  await advance(t, 60_000);
  assert.equal(fake.calls.length, 0);
  assert.equal(fake.pills.get("a").label, "—");
});

test("a pill mounting and the runtime publishing a scope do not multiply reads", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const shared = createSharedStore();
  const runtime = startPillRuntime(fake.deps, createCumulativeHub(), shared);
  t.after(() => runtime.dispose());
  fake.directory([agent("a"), agent("b")]);
  const releases = [shared.claimSurface(WS), shared.claimSurface(WS)];
  t.after(() => releases.forEach((release) => release()));

  assert.equal(shared.surfaceOwns(WS), true);
  fake.settings(scope());
  await advance(t, 60_000);
  // One workspace, one surface-owned read: no runtime request per pill.
  assert.equal(fake.calls.length, 0);
});

test("a surface-read scope the runtime has not seen is adopted, so the label carries its real reason", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const runtime = startPillRuntime(fake.deps, createCumulativeHub());
  t.after(() => runtime.dispose());
  fake.directory([agent("a")]);

  // The pill read the scope through its own surface; the runtime's settings
  // stream never delivered. Handing it over is not a settings change, so the
  // label moves from "…" to the real out-of-allowlist reason.
  assert.equal(runtime.adoptScope(scope({ workspaceIds: ["wks_elsewhere"] })), true);
  await advance(t, 60_000);
  assert.equal(fake.pills.get("a").label, "—");
  assert.match(fake.pills.get("a").title, /不在本机累计名单/);
  assert.equal(fake.calls.length, 0, "an out-of-allowlist workspace reads nothing");

  // A disabled scope is reported the same way and still reads nothing.
  const disabled = fakeClient();
  const off = startPillRuntime(disabled.deps, createCumulativeHub());
  t.after(() => off.dispose());
  disabled.directory([agent("a")]);
  assert.equal(off.adoptScope(scope({ enabled: false })), true);
  await advance(t, 60_000);
  assert.equal(disabled.pills.get("a").label, "—");
  assert.equal(disabled.calls.length, 0);
});

test("the first scope adopted wins, and a followed settings event still owns later changes", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const shared = createSharedStore();
  const runtime = startPillRuntime(fake.deps, createCumulativeHub(), shared);
  t.after(() => runtime.dispose());
  fake.directory([agent("a")]);
  assert.equal(runtime.adoptScope(scope()), true);
  assert.deepEqual(shared.scope()?.workspaceIds, [WS], "the adopted scope is published to the pill");
  assert.equal(runtime.adoptScope(scope({ enabled: false })), false,
    "a second surface adoption cannot displace it");
  fake.settings(scope({ workspaceIds: ["wks_elsewhere"] }));
  assert.equal(fake.pills.get("a").label, "—");
  assert.deepEqual(shared.scope()?.workspaceIds, ["wks_elsewhere"]);
});

test("a late first scope keeps the reading the panel already published", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const hub = createCumulativeHub();
  let resolveFirstRead;
  const deps = {
    ...fake.deps,
    requestScope: () => new Promise((resolve) => { resolveFirstRead = resolve; }),
  };
  const runtime = startPillRuntime(deps, hub, createSharedStore());
  t.after(() => runtime.dispose());
  fake.directory([agent("a")]);
  assert.equal(fake.pills.get("a").label, "…", "nothing has been read yet");

  // The user opened the panel first and its read landed in the shared hub.
  hub.publish(WS, hub.begin(WS), { rate: 0.976, error: null });
  assert.equal(fake.pills.get("a").label, "97.6%");

  // The runtime's own first scope read then answers. It is not a settings
  // change: it must not clear the reading the panel already validated.
  resolveFirstRead(scope());
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "97.6%");
  assert.equal(hub.read(WS)?.rate, 0.976, "the initial scope leaves the hub alone");
  assert.equal(fake.calls.length, 0, "and issues no duplicate read");
});

test("a scope only the panel's settings stream published still starts the runtime", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const shared = createSharedStore();
  const runtime = startPillRuntime(fake.deps, createCumulativeHub(), shared);
  t.after(() => runtime.dispose());
  fake.directory([agent("a")]);
  assert.equal(fake.pills.get("a").label, "…");

  // The panel resolved the scope first; this runtime's own stream never fires.
  shared.setScope(scope(), "live");
  await advance(t, 10_000);
  assert.deepEqual(fake.calls.map(({ type, ...input }) => input),
    [{ workspaceId: WS, agentIds: ["a"], refresh: false }],
    "the runtime reads once from the shared scope");
  fake.pending.shift().resolve(reply(0.976));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "97.6%");

  // A later settings event on this runtime's own stream still owns changes.
  fake.settings(scope({ enabled: false }));
  assert.equal(fake.pills.get("a").label, "—");
});

test("one settings event cannot make the shared key move twice", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const shared = createSharedStore();
  const runtime = startPillRuntime(fake.deps, createCumulativeHub(), shared);
  t.after(() => runtime.dispose());
  fake.directory([agent("a")]);
  fake.settings(scope());
  const first = shared.revision();
  const scopeSeen = shared.scope();

  // The panel's own subscription carries the same event; it must not add a
  // second revision or change the projection behind the pill's back.
  shared.setScope(scopeSeen, "live");
  assert.equal(shared.revision(), first, "a duplicate event does not re-key the read");

  // A retry of the runtime's own stream with an unchanged projection still
  // starts one fresh read: a changed Codex home is not visible in the values.
  fake.settings(scope());
  assert.equal(shared.revision(), first + 1, "an identical projection still reads once");
});

test("a scope read that fails past the pill's short retries still recovers on the runtime's backoff", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const shared = createSharedStore();
  // The settings stream never delivers a first value, and the scope RPC is
  // transiently down for longer than the pill surface's two retries.
  let attempts = 0;
  const deps = {
    ...fake.deps,
    requestScope() {
      attempts += 1;
      if (attempts <= 4) return Promise.reject(new Error("scope rpc transient"));
      return Promise.resolve(scope());
    },
  };
  const runtime = startPillRuntime(deps, createCumulativeHub(), shared);
  t.after(() => runtime.dispose());
  fake.directory([agent("a")]);
  assert.equal(fake.pills.get("a").label, "…");

  // 1s, 2s, 5s, 10s backoff: each failure schedules the next read itself, so
  // the fifth attempt succeeds well after the pill's two short retries.
  for (let step = 0; step < 12 && attempts <= 4; step += 1) await advance(t, 5_000);
  assert.ok(attempts >= 5, "the runtime kept retrying past the pill's short retry");
  await advance(t, 10_000);
  assert.deepEqual(fake.calls.map(({ type, ...input }) => input),
    [{ workspaceId: WS, agentIds: ["a"], refresh: false }],
    "the recovered scope starts the read without any panel");
  fake.pending.shift().resolve(reply(0.976));
  await advance(t, 0);
  assert.equal(fake.pills.get("a").label, "97.6%");
});

test("a terminal refresh in one workspace leaves another workspace's key alone", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const shared = createSharedStore();
  const runtime = startPillRuntime(fake.deps, createCumulativeHub(), shared);
  t.after(() => runtime.dispose());
  const other = { ...agent("z"), workspaceId: "wks_other" };
  fake.settings(scope({ allWorkspaces: true, workspaceIds: [] }));
  fake.directory([agent("a", { status: "running" }), other]);
  const releases = [shared.claimSurface(WS), shared.claimSurface("wks_other")];
  t.after(() => releases.forEach((release) => release()));

  const otherBefore = shared.workspaceRevision("wks_other");
  fake.directory([agent("a", { status: "idle", updatedAt: "2026-11-28T00:00:00Z" }), other]);
  await advance(t, 2_000);
  assert.equal(shared.workspaceRevision(WS), 1);
  assert.equal(shared.workspaceRevision("wks_other"), otherBefore,
    "a finished turn in one workspace does not re-key the other");
});

test("unmounting every pill of one workspace resumes only that workspace's runtime read", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const fake = fakeClient();
  const shared = createSharedStore();
  const runtime = startPillRuntime(fake.deps, createCumulativeHub(), shared);
  t.after(() => runtime.dispose());
  const other = { ...agent("z"), workspaceId: "wks_other_pills" };
  // Two composer pills of the same workspace and one of another are mounted
  // before the settings event, so no runtime read is started at all.
  const releaseA1 = shared.claimSurface(WS);
  const releaseA2 = shared.claimSurface(WS);
  const releaseZ = shared.claimSurface("wks_other_pills");
  t.after(() => [releaseA1, releaseA2, releaseZ].forEach((release) => release()));
  fake.settings(scope({ allWorkspaces: true, workspaceIds: [] }));
  fake.directory([agent("a"), other]);
  await advance(t, 10_000);
  assert.equal(fake.calls.length, 0, "both workspaces are read by their pills");

  // One pill unmounting must not hand the workspace back to a side read.
  releaseA1();
  assert.equal(shared.surfaceOwns(WS), true);
  await advance(t, 60_000);
  assert.equal(fake.calls.length, 0, "a remaining pill still owns the read");

  // The last pill of this workspace unmounts while the other keeps its own.
  releaseA2();
  await advance(t, 10_000);
  assert.deepEqual(fake.calls.map(({ workspaceId }) => workspaceId), [WS],
    "only the workspace that lost its last pill is read again");
});
