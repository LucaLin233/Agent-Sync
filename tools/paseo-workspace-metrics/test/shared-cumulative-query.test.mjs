import assert from "node:assert/strict";
import { test } from "node:test";
import { createCumulativeHub } from "../client/cumulative-hub.ts";
import { createSharedStore, publishPanelScope } from "../client/shared-store.ts";
import {
  cumulativeQueryKey,
  cumulativeReadEnabled,
  readCumulativeIntoHub,
} from "../client/use-cumulative.ts";
import { scopeQueryKey } from "../shared/scope.ts";

const WS = "wks_shared";
const HOST = "host_shared";
const wksScope = (patch = {}) => ({
  enabled: true, workspaceIds: [WS], allWorkspaces: false,
  codexHomeConfigured: true, error: null, ...patch,
});
const reply = (rate, error = null) => ({ rate, error });

const scope = wksScope();

test("the pill and the panel derive one key from the same workspace, members, scope and revision", () => {
  // The panel lists agents newest first; the pill lists them in directory order.
  const panelAgents = [{ id: "b" }, { id: "a" }];
  const pillAgents = [{ id: "a" }, { id: "b" }];
  const panelKey = cumulativeQueryKey(HOST, WS, panelAgents.map(({ id }) => id), scopeQueryKey(scope), 0, 0);
  const pillKey = cumulativeQueryKey(HOST, WS, pillAgents.map(({ id }) => id), scopeQueryKey(scope), 0, 0);
  assert.deepEqual(panelKey, pillKey);
  assert.deepEqual(panelKey, ["workspace-metrics-cumulative", HOST, WS, ["a", "b"],
    "true|false|wks_shared|true|", 0, 0]);
});

test("another host, workspace, member set, settings value or refresh revision is another key", () => {
  const base = cumulativeQueryKey(HOST, WS, ["a"], scopeQueryKey(scope), 0, 0);
  assert.notDeepEqual(cumulativeQueryKey("host_other", WS, ["a"], scopeQueryKey(scope), 0, 0), base);
  assert.notDeepEqual(cumulativeQueryKey(HOST, "wks_other", ["a"], scopeQueryKey(scope), 0, 0), base);
  assert.notDeepEqual(cumulativeQueryKey(HOST, WS, ["a", "b"], scopeQueryKey(scope), 0, 0), base);
  assert.notDeepEqual(cumulativeQueryKey(HOST, WS, ["a"], scopeQueryKey(wksScope({ enabled: false })), 0, 0), base);
  assert.notDeepEqual(cumulativeQueryKey(HOST, WS, ["a"], scopeQueryKey(scope), 1, 0), base);
  assert.notDeepEqual(cumulativeQueryKey(HOST, WS, ["a"], scopeQueryKey(scope), 0, 1), base);
  // A settings change that leaves the effective values identical keeps the key.
  assert.deepEqual(cumulativeQueryKey(HOST, WS, ["a"], scopeQueryKey(wksScope()), 0, 0), base);
});

test("a closed setting, an out-of-allowlist workspace or an unresolved scope reads nothing", () => {
  assert.equal(cumulativeReadEnabled(scope, WS), true);
  assert.equal(cumulativeReadEnabled(wksScope({ allWorkspaces: true, workspaceIds: [] }), "wks_any"), true);
  assert.equal(cumulativeReadEnabled(wksScope({ enabled: false }), WS), false);
  assert.equal(cumulativeReadEnabled(wksScope({ workspaceIds: ["wks_other"] }), WS), false);
  // A saved setting that enables the feature with an empty allowlist is an error
  // whose scope lists no workspace: the read stays gated.
  assert.equal(cumulativeReadEnabled(wksScope({
    workspaceIds: [], error: "至少填写一个 workspace ID",
  }), WS), false);
  assert.equal(cumulativeReadEnabled(null, WS), false);
  // The pending key never equals a resolved one, so a placeholder cannot reuse it.
  assert.notEqual(scopeQueryKey(null), scopeQueryKey(scope));
});

test("every reply feeds the shared label, including a real zero, a missing snapshot and a failure", async () => {
  const hub = createCumulativeHub();
  await readCumulativeIntoHub({ run: async () => reply(0.976), hub, workspaceId: WS, agentIds: ["a"], refresh: false });
  assert.deepEqual(hub.read(WS), { rate: 0.976, error: null });

  await readCumulativeIntoHub({ run: async () => reply(0), hub, workspaceId: WS, agentIds: ["a"], refresh: false });
  assert.deepEqual(hub.read(WS), { rate: 0, error: null }, "a real zero is a measurement");

  await readCumulativeIntoHub({ run: async () => reply(null), hub, workspaceId: WS, agentIds: ["a"], refresh: false });
  assert.deepEqual(hub.read(WS), { rate: null, error: null });

  await readCumulativeIntoHub({ run: async () => reply(null, "读取失败"), hub, workspaceId: WS, agentIds: ["a"], refresh: false });
  assert.deepEqual(hub.read(WS), { rate: null, error: "读取失败" });

  const failing = createCumulativeHub();
  await assert.rejects(readCumulativeIntoHub({
    run: async () => { throw new Error("rpc down"); },
    hub: failing, workspaceId: WS, agentIds: ["a"], refresh: false,
  }));
  assert.deepEqual(failing.read(WS), { rate: null, error: "累计用量读取失败" },
    "a failed read leaves \"…\" for its own reason");
});

test("the read is issued once per call from the current members, and a refresh bypasses the cache", async () => {
  const hub = createCumulativeHub();
  const calls = [];
  const run = async (input) => { calls.push(input); return reply(0.5); };
  await readCumulativeIntoHub({ run, hub, workspaceId: WS, agentIds: ["b", "a"], refresh: false });
  await readCumulativeIntoHub({ run, hub, workspaceId: WS, agentIds: ["a", "b"], refresh: true });
  assert.deepEqual(calls, [
    { workspaceId: WS, agentIds: ["b", "a"], refresh: false },
    { workspaceId: WS, agentIds: ["a", "b"], refresh: true },
  ]);
});

test("a mounted surface owns the workspace until its last pill unmounts", () => {
  const shared = createSharedStore();
  assert.equal(shared.surfaceOwns(WS), false);
  const releaseFirst = shared.claimSurface(WS);
  const releaseSecond = shared.claimSurface(WS);
  assert.equal(shared.surfaceOwns(WS), true);
  releaseFirst();
  assert.equal(shared.surfaceOwns(WS), true, "one mounted pill still owns the read");
  releaseSecond();
  assert.equal(shared.surfaceOwns(WS), false);
  releaseSecond();
  assert.equal(shared.surfaceOwns(WS), false, "a repeated release changes nothing");
});

test("a settings change replaces the shared scope and gating uses it immediately", () => {
  const shared = createSharedStore();
  const seen = [];
  const unsubscribe = shared.subscribe(() => seen.push(shared.scope()));
  shared.setScope(scope, "live");
  shared.setScope(scope, "live");
  assert.equal(seen.length, 1, "the same scope is published once");
  shared.setScope(wksScope({ enabled: false }), "live");
  assert.equal(seen.length, 2);
  assert.equal(cumulativeReadEnabled(shared.scope(), WS), false);
  unsubscribe();
  shared.setScope(scope, "live");
  assert.equal(seen.length, 2, "an unsubscribed surface no longer hears changes");
});

test("a revision bump moves both surfaces to one new read and carries the refresh intent", () => {
  const shared = createSharedStore();
  const key = () => cumulativeQueryKey(
    HOST, WS, ["a"], scopeQueryKey(scope), shared.revision(), shared.workspaceRevision(WS));
  const before = key();
  shared.bumpWorkspace(WS);
  const routine = shared.workspaceRevision(WS);
  assert.equal(shared.refreshIntent(WS, routine), false);
  assert.notDeepEqual(key(), before);
  shared.bumpWorkspace(WS, true);
  assert.equal(shared.refreshIntent(WS, shared.workspaceRevision(WS)), true);
  assert.equal(shared.refreshIntent(WS, routine), false, "a routine revision keeps its own, non-bypassing read");
  assert.notDeepEqual(key(), before);
  // A refresh of this workspace does not move another workspace's key.
  assert.deepEqual(
    cumulativeQueryKey(HOST, "wks_other", ["a"], scopeQueryKey(scope), shared.revision(), shared.workspaceRevision("wks_other")),
    cumulativeQueryKey(HOST, "wks_other", ["a"], scopeQueryKey(scope), 0, 0),
  );
});

test("one settings event that changes the projection moves the key exactly once", () => {
  const shared = createSharedStore();
  const key = () => cumulativeQueryKey(HOST, WS, ["a"], scopeQueryKey(shared.scope()), shared.revision());
  shared.setScope(scope, "live");
  const first = key();
  // The runtime and the open panel each carry this event; only the first one
  // changes the projection, so the second copy must not move the key again.
  shared.setScope(wksScope({ workspaceIds: [WS, "wks_two"] }), "live");
  shared.setScope(wksScope({ workspaceIds: [WS, "wks_two"] }), "live");
  const after = key();
  assert.notDeepEqual(after, first, "the settings projection alone is a new key");
  assert.equal(shared.revision(), 0, "a projection change needs no revision");
});

test("a changed Codex home moves the key once, and a duplicate event does nothing", () => {
  const shared = createSharedStore();
  const key = () => cumulativeQueryKey(HOST, WS, ["a"], scopeQueryKey(shared.scope()), shared.revision());
  shared.setScope(scope, "live");
  const first = key();
  // A changed Codex home returns different rollouts with the same allowlist.
  shared.setScope(wksScope({ codexHomeConfigured: false }), "live");
  const second = key();
  assert.notDeepEqual(second, first, "the Codex home is part of the settings identity");
  // The panel's duplicate copy of the same event must not re-request.
  shared.setScope(wksScope({ codexHomeConfigured: false }), "live");
  assert.deepEqual(key(), second);
});

test("clearing the old generation before publishing the scope keeps the new read alive", () => {
  // Publishing a scope notifies subscribers synchronously, and a surface can
  // start its read for the new key inside that notification. If the generation
  // were cleared after publishing, that brand-new reply would be voided and the
  // label would stay empty until the next refresh. Clearing first is correct.
  const run = (clearFirst) => {
    const hub = createCumulativeHub();
    const shared = createSharedStore();
    shared.setScope(scope, "live");
    const oldTicket = hub.begin(WS);
    let newTicket;
    const unsubscribe = shared.subscribe(() => { newTicket = hub.begin(WS); });
    if (clearFirst) hub.clearAll();
    shared.setScope(wksScope({ workspaceIds: [WS, "wks_two"] }), "live", true);
    if (!clearFirst) hub.clearAll();
    unsubscribe();
    return {
      old: hub.publish(WS, oldTicket, { rate: 0.5, error: null }),
      fresh: hub.publish(WS, newTicket, { rate: 0.976, error: null }),
      shown: hub.read(WS),
    };
  };

  const fixed = run(true);
  assert.equal(fixed.old, false, "a reply from the old settings generation cannot land");
  assert.equal(fixed.fresh, true, "the new generation's first reply survives the event");
  assert.equal(fixed.shown?.rate, 0.976);

  const reversed = run(false);
  assert.equal(reversed.old, false);
  assert.equal(reversed.fresh, false, "publishing before the clear would void the new reply");
  assert.equal(reversed.shown, undefined);
});

test("a failed shared scope gates the read until the panel's event is adopted", () => {
  const shared = createSharedStore();
  const placeholder = {
    enabled: false, workspaceIds: [], allWorkspaces: false,
    codexHomeConfigured: false, error: "设置订阅已关闭",
  };
  shared.setScope(placeholder, "failed");
  // The panel's own setting is not read around the shared scope; it has to
  // become the shared scope first, so both surfaces key on one value.
  assert.equal(cumulativeReadEnabled(shared.scope(), WS), false);
  publishPanelScope(shared, wksScope());
  assert.equal(shared.scopeStatus(), "live");
  assert.equal(cumulativeReadEnabled(shared.scope(), WS), true);
});

test("the panel's event replaces a failed scope in the shared store, a live one is left to the runtime", () => {
  const shared = createSharedStore();
  const failed = {
    enabled: false, workspaceIds: [], allWorkspaces: false,
    codexHomeConfigured: false, error: "设置订阅已关闭",
  };
  shared.setScope(failed, "failed");
  publishPanelScope(shared, wksScope());
  assert.equal(shared.scopeStatus(), "live");
  assert.equal(cumulativeReadEnabled(shared.scope(), WS), true);

  // The runtime's stream is down, so a later panel event still flows through.
  assert.equal(shared.runtimeStreamLive(), false);
  publishPanelScope(shared, wksScope({ workspaceIds: [WS, "wks_three"] }));
  assert.deepEqual(shared.scope()?.workspaceIds, [WS, "wks_three"]);

  // Once the runtime's own stream delivers, the panel's copy is a duplicate of
  // the same event and must not re-key the read a second time.
  shared.setRuntimeStreamLive(true);
  shared.setScope(wksScope(), "live");
  const revision = shared.revision();
  const scope = shared.scope();
  publishPanelScope(shared, wksScope({ workspaceIds: [WS, "wks_four"] }));
  assert.equal(shared.revision(), revision);
  assert.equal(shared.scope(), scope, "the runtime's live scope is retained");
});
