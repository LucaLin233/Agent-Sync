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
