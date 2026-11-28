import "./client-env.mjs";
import assert from "node:assert/strict";
import { test } from "node:test";
import { QueryClient, QueryObserver } from "@tanstack/react-query";
import { createCumulativeHub } from "../client/cumulative-hub.ts";
import { cumulativeQueryOptions, CUMULATIVE_ERROR_RETRY_MS } from "../client/use-cumulative.ts";
import { scopeQueryKey } from "../shared/scope.ts";

const HOST = "host_mount";
const WS = "wks_mount";
const scope = {
  enabled: true, workspaceIds: [WS], allWorkspaces: false,
  codexHomeConfigured: true, error: null,
};
const reply = (rate) => ({
  workspaceId: WS, inputTokens: 100, cachedInputTokens: 98, covered: 1, eligible: 1,
  missing: 0, unavailable: 0, rate, error: null, latestSamples: [], recentTurn: null,
  turns: { sessions: 1, completed: 1, speedSamples: 0, firstTokenSamples: 0,
    outputTokens: 0, elapsedMs: 0, firstTokenTotalMs: 0 },
});

const flush = async () => {
  for (let i = 0; i < 5; i += 1) await Promise.resolve();
  await new Promise((resolve) => setImmediate(resolve));
};

/** The real query the composer pill mounts, driven by a real QueryObserver. */
function mount(input) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const observer = new QueryObserver(client, cumulativeQueryOptions(input));
  const seen = [];
  const unsubscribe = observer.subscribe((result) => seen.push(result));
  const stop = () => {
    unsubscribe();
    observer.destroy();
    client.clear();
  };
  return { client, observer, seen, stop };
}

test("a mounting pill whose first cumulative read fails retries itself and fills 97.6% with no panel", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval", "Date"] });
  const hub = createCumulativeHub();
  let calls = 0;
  const run = () => {
    calls += 1;
    // The connection is not settled yet: the very first read is rejected.
    if (calls === 1) return Promise.reject(new Error("connection not ready"));
    return Promise.resolve(reply(0.976));
  };
  const { seen, stop } = mount({
    hostId: HOST,
    workspaceId: WS,
    agentIds: ["a"],
    enabled: true,
    scopeKey: scopeQueryKey(scope),
    settingsRevision: 0,
    workspaceRevision: 0,
    hub,
    run,
  });
  t.after(stop);

  await flush();
  assert.equal(calls, 1, "the mount issues exactly one read");
  assert.equal(seen.at(-1).status, "error", "and the failed read is visible as an error");
  assert.match(seen.at(-1).error.message, /connection not ready/);
  assert.equal(hub.read(WS)?.error, "累计用量读取失败", "the label leaves … for a real reason");

  // Nothing else happens: no member change, no panel, no manual refresh. Only
  // this workspace's query retries itself, once the failure interval passes.
  t.mock.timers.tick(CUMULATIVE_ERROR_RETRY_MS - 1);
  await flush();
  assert.equal(calls, 1, "it does not spin faster than the error interval");
  t.mock.timers.tick(1);
  await flush();
  assert.equal(calls, 2, "the failed read is re-issued on its own");
  assert.equal(seen.at(-1).status, "success");
  assert.equal(seen.at(-1).data.rate, 0.976);
  assert.deepEqual(hub.read(WS), { rate: 0.976, error: null }, "the label now shows 97.6%");

  // A successful read stops the retry loop: the interval reports false.
  t.mock.timers.tick(CUMULATIVE_ERROR_RETRY_MS * 4);
  await flush();
  assert.equal(calls, 2, "no periodic polling once a reading exists");
});

test("disabled settings or an out-of-allowlist workspace never reads or retries", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval", "Date"] });
  const hub = createCumulativeHub();
  let calls = 0;
  const run = () => {
    calls += 1;
    return Promise.reject(new Error("must not be called"));
  };
  const options = {
    hostId: HOST,
    workspaceId: WS,
    agentIds: ["a"],
    scopeKey: scopeQueryKey({ ...scope, enabled: false }),
    settingsRevision: 0,
    workspaceRevision: 0,
    hub,
    run,
  };
  const { seen, stop } = mount({ ...options, enabled: false });
  t.after(stop);
  await flush();
  t.mock.timers.tick(CUMULATIVE_ERROR_RETRY_MS * 3);
  await flush();
  assert.equal(calls, 0);
  assert.equal(seen.length, 0, "a gated query produces no request and no retry");
});

test("a retry of a failed read bypasses the server cache and stays on this workspace's key", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval", "Date"] });
  const hub = createCumulativeHub();
  const requests = [];
  let calls = 0;
  const run = (input) => {
    calls += 1;
    requests.push(input);
    if (calls === 1) return Promise.reject(new Error("transient"));
    return Promise.resolve(reply(0));
  };
  const { client, seen, stop } = mount({
    hostId: HOST,
    workspaceId: WS,
    agentIds: ["a"],
    enabled: true,
    scopeKey: scopeQueryKey(scope),
    settingsRevision: 0,
    workspaceRevision: 0,
    hub,
    run,
    bypassCache: true,
  });
  t.after(stop);
  await flush();
  t.mock.timers.tick(CUMULATIVE_ERROR_RETRY_MS);
  await flush();

  assert.equal(calls, 2);
  assert.deepEqual(requests.map(({ workspaceId, agentIds, refresh }) => ({ workspaceId, agentIds, refresh })),
    [{ workspaceId: WS, agentIds: ["a"], refresh: true },
      { workspaceId: WS, agentIds: ["a"], refresh: true }],
    "every read stays in the target workspace and honours the cache bypass");
  assert.equal(seen.at(-1).data.rate, 0);
  assert.deepEqual(hub.read(WS), { rate: 0, error: null }, "a real zero is a reading, not a failure");
  const cacheKeys = client.getQueryCache().getAll().map((query) => query.queryKey);
  assert.equal(cacheKeys.length, 1, "one cache entry, not one per attempt");
  assert.equal(cacheKeys[0][0], "workspace-metrics-cumulative");
  assert.equal(cacheKeys[0][2], WS, "and it belongs to the mounted workspace only");
});

test("a closed runtime stream no longer masks the popover's own settings event", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval", "Date"] });
  const { createSharedStore, publishPanelScope } = await import("../client/shared-store.ts");
  const { cumulativeReadEnabled } = await import("../client/use-cumulative.ts");

  const shared = createSharedStore();
  const placeholder = {
    enabled: false, workspaceIds: [], allWorkspaces: false,
    codexHomeConfigured: false, error: "设置订阅已关闭",
  };
  shared.setScope(placeholder, "failed");

  let calls = 0;
  const hub = createCumulativeHub();
  const read = (scope) => mount({
    hostId: HOST,
    workspaceId: WS,
    agentIds: ["a"],
    enabled: cumulativeReadEnabled(scope, WS),
    scopeKey: scopeQueryKey(scope),
    settingsRevision: shared.revision(),
    workspaceRevision: shared.workspaceRevision(WS),
    hub,
    run: async () => { calls += 1; return reply(0.976); },
  });

  // With only the runtime's failed placeholder, the popover reads nothing.
  const gated = read(shared.scope());
  t.after(gated.stop);
  await flush();
  assert.equal(calls, 0, "a failed placeholder alone gates the read off");

  // The panel's own subscription then delivers usable settings, which is what
  // the user reaches by simply opening the popover (no other action). The
  // panel hands it to the runtime, so the shared scope itself becomes usable.
  publishPanelScope(shared, { ...scope });
  const live = read(shared.scope());
  t.after(live.stop);
  await flush();
  assert.equal(calls, 1, "opening the popover still issues the real read");
  assert.equal(live.observer.getCurrentResult().data.rate, 0.976);
  assert.deepEqual(hub.read(WS), { rate: 0.976, error: null },
    "and the composer pill shows it too");
});

test("a second close is not bridged by the panel's previous event", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval", "Date"] });
  const { createSharedStore, publishPanelScope } = await import("../client/shared-store.ts");
  const { cumulativeReadEnabled } = await import("../client/use-cumulative.ts");

  const shared = createSharedStore();
  const placeholder = {
    enabled: false, workspaceIds: [], allWorkspaces: false,
    codexHomeConfigured: false, error: "设置订阅已关闭",
  };
  shared.setScope(placeholder, "failed");
  const panelEvent = { ...scope };
  publishPanelScope(shared, panelEvent);
  assert.equal(cumulativeReadEnabled(shared.scope(), WS), true,
    "the panel's own event enables the read");

  // The runtime's stream closes again. The earlier event is history, not a
  // live setting: the cumulative read must gate off until a new event lands,
  // and the popover's stale copy must not be reused in its place.
  shared.setScope(placeholder, "failed");
  // This is exactly what the removed `localScope` fallback would have done:
  // keep reading the old allowlist until the panel's stream speaks again.
  assert.equal(cumulativeReadEnabled(panelEvent, WS), true,
    "the removed fallback would have read the old allowlist");
  assert.equal(cumulativeReadEnabled(shared.scope(), WS), false,
    "a second close gates the read instead of reviving the old allowlist");
  assert.equal(shared.scopeStatus(), "failed");

  // A fresh event from the panel's own stream is what turns it back on.
  publishPanelScope(shared, { ...scope });
  assert.equal(cumulativeReadEnabled(shared.scope(), WS), true);
  assert.equal(shared.scopeStatus(), "live");
});

test("opening the panel after the pill read shares its key instead of reading twice", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval", "Date"] });
  const { createSharedStore, publishPanelScope } = await import("../client/shared-store.ts");
  const { cumulativeReadEnabled } = await import("../client/use-cumulative.ts");

  const shared = createSharedStore();
  const hub = createCumulativeHub();
  // The runtime's settings stream closed and left its placeholder.
  shared.setScope({
    enabled: false, workspaceIds: [], allWorkspaces: false,
    codexHomeConfigured: false, error: "设置订阅已关闭",
  }, "failed");

  // The pill mounted first, with no scope: nothing to read yet.
  let calls = 0;
  const options = () => {
    const scope = shared.scope();
    return {
      hostId: HOST,
      workspaceId: WS,
      agentIds: ["a"],
      enabled: cumulativeReadEnabled(scope, WS),
      scopeKey: scopeQueryKey(scope),
      settingsRevision: shared.revision(),
      workspaceRevision: shared.workspaceRevision(WS),
      hub,
      run: async () => { calls += 1; return reply(0.976); },
    };
  };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const pill = new QueryObserver(client, cumulativeQueryOptions(options()));
  const seen = [];
  pill.subscribe((result) => seen.push(result));
  t.after(() => { pill.destroy(); client.clear(); });
  await flush();
  assert.equal(calls, 0, "a failed placeholder gates the pill off");

  // The panel's own stream delivers the real settings while the pill is
  // mounted. One generation, and both surfaces now share that key.
  publishPanelScope(shared, { ...scope });
  pill.setOptions(cumulativeQueryOptions(options()));
  t.mock.timers.tick(0);
  await flush();
  assert.equal(calls, 1, "the pill reads once for the panel's settings");

  const popover = new QueryObserver(client, cumulativeQueryOptions(options()));
  popover.subscribe(() => {});
  t.after(() => popover.destroy());
  t.mock.timers.tick(0);
  await flush();
  assert.equal(calls, 1, "opening the popover observes the same cached query");
  const popoverData = popover.getCurrentResult().data;
  assert.equal(popoverData.rate, 0.976, "the popover already holds the pill's reading");
  assert.deepEqual(seen.at(-1).data, popoverData, "both surfaces see the same cached reply");
  const cumulativeEntries = client.getQueryCache().getAll()
    .filter((query) => query.queryKey[0] === "workspace-metrics-cumulative");
  // The gated mount left one never-fetched placeholder key; the real reading is
  // one entry both surfaces observe — not one per surface.
  assert.equal(cumulativeEntries.filter((query) => query.state.data !== undefined).length, 1,
    "one fetched cumulative cache entry for the pill and the popover");
  assert.equal(cumulativeEntries.filter((query) => query.state.status === "error").length, 0);
});
