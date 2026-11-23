import assert from "node:assert/strict";
import { test } from "node:test";
import { promises as fs } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { clearCumulativeCaches, clearCumulativeRequestCache, collectCumulativeUsage, collectTurnOutput, createScopeSubscriptionHandler, resolveCodexHome, workspaceScope } from "../server/cumulative.ts";

const WS = "wks_test";
const uuid = (n) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
const token = (input, cached) => JSON.stringify({
  timestamp: "2026-11-22T00:00:00Z",
  type: "event_msg",
  payload: {
    type: "token_count",
    info: { total_token_usage: { input_tokens: input, cached_input_tokens: cached, output_tokens: 0 } },
  },
});
const other = JSON.stringify({ type: "response_item", payload: { type: "message", content: [] } });

const at = (second) => `2026-11-22T00:00:${String(second).padStart(2, "0")}Z`;
const turnStarted = (id, second) => JSON.stringify({
  timestamp: at(second), type: "event_msg", payload: { type: "task_started", turn_id: id },
});
// task_complete may carry assistant text upstream; the reader must ignore it.
const turnComplete = (id, second, extra = {}) => JSON.stringify({
  timestamp: at(second),
  type: "event_msg",
  payload: { type: "task_complete", turn_id: id, last_agent_message: "ignore me", ...extra },
});
const turnEvent = (type, second) => JSON.stringify({
  timestamp: at(second), type: "event_msg", payload: { type },
});
const tokenAt = (second, input, cached, output) => JSON.stringify({
  timestamp: at(second),
  type: "event_msg",
  payload: {
    type: "token_count",
    info: { total_token_usage: { input_tokens: input, cached_input_tokens: cached, output_tokens: output } },
  },
});

async function runTurn(root, snapshots, agentId = snapshots[0].agent.id) {
  return collectTurnOutput(
    { workspaceId: WS, agentId },
    paseoFor(snapshots),
    { codexHome: root, workspaceIds: [WS] },
  );
}

async function makeRoot(t) {
  const root = await fs.mkdtemp(join(tmpdir(), "workspace-metrics-cumulative-"));
  t.after(async () => { await fs.rm(root, { recursive: true, force: true }); });
  await fs.mkdir(join(root, "sessions", "2026", "11", "22"), { recursive: true });
  await fs.mkdir(join(root, "archived_sessions"), { recursive: true });
  return root;
}

async function makeHome(t) {
  const base = await fs.mkdtemp(join(tmpdir(), "workspace-metrics-home-"));
  t.after(async () => { await fs.rm(base, { recursive: true, force: true }); });
  const home = join(base, "home");
  await fs.mkdir(home, { recursive: true });
  return { base, home };
}

async function makeCodexRoot(parent, name) {
  const root = join(parent, name);
  await fs.mkdir(join(root, "sessions", "2026", "11", "22"), { recursive: true });
  await fs.mkdir(join(root, "archived_sessions"), { recursive: true });
  return root;
}

function settingsFor(values) {
  return { read: async () => ({ status: "ready", values }) };
}

function sessionFile(root, id, sub = "sessions/2026/11/22") {
  return join(root, sub, `rollout-2026-11-22T00-00-00-${id}.jsonl`);
}

async function writeSession(root, id, lines, sub) {
  const file = sessionFile(root, id, sub);
  await fs.writeFile(file, lines.join("\n") + "\n");
  return file;
}

function snapshot(id, nativeHandle, overrides = {}) {
  return {
    agent: {
      id,
      workspaceId: WS,
      provider: "cchp",
      archivedAt: null,
      createdAt: "2026-11-22T00:00:00Z",
      persistence: { nativeHandle, metadata: { provider: "codex" } },
      ...overrides,
    },
  };
}

function paseoFor(snapshots) {
  const byId = new Map(snapshots.map(({ agent }) => [agent.id, { agent }]));
  return {
    agents: {
      ref(id) {
        return { refresh: async () => byId.get(id) ?? null };
      },
    },
  };
}

async function run(root, snapshots) {
  return collectCumulativeUsage(
    { workspaceId: WS, agentIds: snapshots.map(({ agent }) => agent.id) },
    paseoFor(snapshots),
    { codexHome: root, workspaceIds: [WS] },
  );
}

test("uses each session's latest cumulative snapshot and weights the total", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const a = uuid(1);
  const b = uuid(2);
  await writeSession(root, a, [
    other,
    token(100, 90),
    token(1_000, 900),
  ]);
  await writeSession(root, b, [token(500, 250)]);
  const result = await run(root, [
    snapshot("agent-a", a),
    snapshot("agent-b", b),
  ]);
  assert.deepEqual(result, {
    workspaceId: WS,
    inputTokens: 1_500,
    cachedInputTokens: 1_150,
    covered: 2,
    eligible: 2,
    missing: 0,
    unavailable: 0,
    rate: 1_150 / 1_500,
    error: null,
  });
});

test("duplicate native handles count once and are not summed", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const a = uuid(1);
  await writeSession(root, a, [token(100, 50)]);
  const result = await run(root, [
    snapshot("agent-a", a),
    snapshot("agent-b", a),
  ]);
  assert.equal(result.covered, 1);
  assert.equal(result.eligible, 1);
  assert.equal(result.inputTokens, 100);
  assert.equal(result.cachedInputTokens, 50);
});

test("closed sessions count, archived and cross-workspace sessions are rejected", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const a = uuid(1);
  await writeSession(root, a, [token(100, 50)]);
  const result = await run(root, [
    snapshot("agent-closed", a),
    snapshot("agent-archived", uuid(2), { archivedAt: "2026-11-22T00:00:00Z" }),
    snapshot("agent-other", uuid(3), { workspaceId: "wks_other" }),
  ]);
  assert.equal(result.covered, 1);
  assert.equal(result.eligible, 1);
  assert.equal(result.unavailable, 2);
  assert.equal(result.error, null);
});

test("missing files and invalid cumulative values stay missing, never zero", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const missing = uuid(1);
  const invalid = uuid(2);
  await writeSession(root, invalid, [
    JSON.stringify({ type: "event_msg", payload: { type: "token_count", info: null } }),
    token(50, 51),
    token(-1, 0),
  ]);
  const result = await run(root, [
    snapshot("agent-missing", missing),
    snapshot("agent-invalid", invalid),
  ]);
  assert.equal(result.covered, 0);
  assert.equal(result.eligible, 2);
  assert.equal(result.missing, 2);
  assert.equal(result.rate, null);
  assert.equal(result.error, null);
});

test("incremental append replaces the snapshot instead of adding it", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const a = uuid(1);
  const file = sessionFile(root, a);
  const first = token(100, 50) + "\n";
  const second = token(200, 150) + "\n";
  await fs.writeFile(file, first);
  const before = await run(root, [snapshot("agent-a", a)]);
  assert.equal(before.inputTokens, 100);
  const split = Math.floor(second.length / 2);
  await fs.appendFile(file, second.slice(0, split));
  clearCumulativeRequestCache();
  const partial = await run(root, [snapshot("agent-a", a)]);
  assert.equal(partial.inputTokens, 100);
  await fs.appendFile(file, second.slice(split));
  clearCumulativeRequestCache();
  const after = await run(root, [snapshot("agent-a", a)]);
  assert.equal(after.inputTokens, 200);
  assert.equal(after.cachedInputTokens, 150);
});

test("symlinked session files are skipped", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const a = uuid(1);
  const outside = join(root, "outside.jsonl");
  await fs.writeFile(outside, token(100, 50) + "\n");
  await fs.symlink(outside, sessionFile(root, a));
  const result = await run(root, [snapshot("agent-a", a)]);
  assert.equal(result.covered, 0);
  assert.equal(result.missing, 1);
});

test("an unavailable data root reports an explicit error", async (t) => {
  clearCumulativeCaches();
  const root = join(tmpdir(), `workspace-metrics-missing-${Date.now()}`);
  const result = await run(root, [snapshot("agent-a", uuid(1))]);
  assert.equal(result.covered, 0);
  assert.equal(result.eligible, 1);
  assert.notEqual(result.error, null);
});

test("non-Codex sessions are not eligible", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const result = await run(root, [
    snapshot("agent-claude", uuid(1), {
      provider: "claude",
      persistence: { nativeHandle: uuid(1), metadata: {} },
    }),
  ]);
  assert.equal(result.eligible, 0);
  assert.equal(result.unavailable, 1);
  assert.notEqual(result.error, null);
});

test("workspace allowlist refuses other workspaces before reading sessions", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const result = await collectCumulativeUsage(
    { workspaceId: "wks_other", agentIds: ["agent-a"] },
    paseoFor([snapshot("agent-a", uuid(1))]),
    { codexHome: root, workspaceIds: [WS] },
  );
  assert.equal(result.eligible, 0);
  assert.equal(result.covered, 0);
  assert.equal(result.error, "当前 workspace 不在本机累计用量允许范围");
});

test("no configured workspace allowlist disables cumulative reads", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const result = await collectCumulativeUsage(
    { workspaceId: WS, agentIds: ["agent-a"] },
    paseoFor([snapshot("agent-a", uuid(1))]),
    { codexHome: root },
  );
  assert.equal(result.eligible, 0);
  assert.equal(result.error, "累计统计未启用");
});

test("a same-length in-place replacement is parsed again", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const a = uuid(1);
  const file = sessionFile(root, a);
  await fs.writeFile(file, token(100, 50) + "\n");
  assert.equal((await run(root, [snapshot("agent-a", a)])).inputTokens, 100);
  await new Promise((resolve) => setTimeout(resolve, 25));
  await fs.writeFile(file, token(900, 80) + "\n");
  clearCumulativeRequestCache();
  const after = await run(root, [snapshot("agent-a", a)]);
  assert.equal(after.inputTokens, 900);
  assert.equal(after.cachedInputTokens, 80);
});

test("only date directories near the trusted creation date are consulted", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const a = uuid(1);
  await fs.mkdir(join(root, "sessions", "2020", "01", "01"), { recursive: true });
  await writeSession(root, a, [token(100, 50)], "sessions/2020/01/01");
  const result = await run(root, [snapshot("agent-a", a)]);
  assert.equal(result.covered, 0);
  assert.equal(result.missing, 1);
});

test("a symlinked date directory is not followed", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const a = uuid(1);
  const outside = join(root, "outside-dir");
  await fs.mkdir(outside);
  await fs.writeFile(join(outside, `rollout-2026-11-22T00-00-00-${a}.jsonl`), token(100, 50) + "\n");
  await fs.symlink(outside, join(root, "sessions", "2026", "11", "23"));
  const result = await run(root, [snapshot("agent-a", a)]);
  assert.equal(result.covered, 0);
  assert.equal(result.missing, 1);
});

test("plugin codexHome must stay inside the daemon user's home", async (t) => {
  const { base, home } = await makeHome(t);
  const inside = await makeCodexRoot(home, "codex-real");
  const insideLink = join(home, "codex-link");
  await fs.symlink(inside, insideLink);
  const outside = await makeCodexRoot(base, "outside");
  const outsideLink = join(home, "codex-outside");
  await fs.symlink(outside, outsideLink);

  const accepted = await resolveCodexHome(settingsFor({ codexHome: insideLink }), { home, env: "" });
  assert.equal(accepted.root, await fs.realpath(inside));
  const rejected = await resolveCodexHome(settingsFor({ codexHome: outsideLink }), { home, env: "" });
  assert.equal(rejected.root, null);
});

test("daemon CODEX_HOME keeps an external root and rejects a symlink escape", async (t) => {
  const { base, home } = await makeHome(t);
  const parent = join(base, "roots");
  const external = await makeCodexRoot(parent, "codex");
  const accepted = await resolveCodexHome(undefined, { home, env: external });
  assert.equal(accepted.root, await fs.realpath(external));

  const outside = await makeCodexRoot(base, "outside");
  const escaping = join(parent, "escaping");
  await fs.symlink(outside, escaping);
  const rejected = await resolveCodexHome(undefined, { home, env: escaping });
  assert.equal(rejected.root, null);

  const inside = await makeCodexRoot(parent, "inside");
  const linked = join(parent, "linked");
  await fs.symlink(inside, linked);
  const linkedAccepted = await resolveCodexHome(undefined, { home, env: linked });
  assert.equal(linkedAccepted.root, await fs.realpath(inside));
});

test("the default Codex root remains under the daemon user's home", async (t) => {
  const { home } = await makeHome(t);
  const root = await makeCodexRoot(home, ".codex");
  const result = await resolveCodexHome(settingsFor({}), { home, env: "" });
  assert.equal(result.root, await fs.realpath(root));
});

test("manual codexHome overrides CODEX_HOME and invalid manual values do not fall back", async (t) => {
  const { base, home } = await makeHome(t);
  const external = await makeCodexRoot(join(base, "roots"), "env-codex");
  const manual = await makeCodexRoot(home, "manual-codex");
  const preferred = await resolveCodexHome(settingsFor({ codexHome: manual }), { home, env: external });
  assert.equal(preferred.root, await fs.realpath(manual));
  assert.equal(preferred.error, null);

  const missing = await resolveCodexHome(
    settingsFor({ codexHome: join(home, "missing-codex") }),
    { home, env: external },
  );
  assert.equal(missing.root, null);
  assert.match(missing.error, /不存在或不可读/);

  const relative = await resolveCodexHome(settingsFor({ codexHome: "codex" }), { home, env: external });
  assert.equal(relative.root, null);
  assert.match(relative.error, /绝对路径/);
});

test("settings default to the explicit allowlist and refuse other workspaces", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const result = await collectCumulativeUsage(
    { workspaceId: "wks_other", agentIds: ["agent-a"] },
    paseoFor([snapshot("agent-a", uuid(1))]),
    { codexHome: root, settings: settingsFor({ workspaceIds: [WS] }) },
  );
  assert.equal(result.eligible, 0);
  assert.equal(result.error, "当前 workspace 不在本机累计用量允许范围");
});

test("allWorkspaces totals two workspaces separately and never mixes them", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const a = uuid(1);
  const b = uuid(2);
  await writeSession(root, a, [token(100, 90)]);
  await writeSession(root, b, [token(400, 100)]);
  const snapshots = [snapshot("agent-a", a), snapshot("agent-b", b, { workspaceId: "wks_two" })];
  const first = await collectCumulativeUsage(
    { workspaceId: WS, agentIds: ["agent-a"] },
    paseoFor(snapshots),
    { codexHome: root, allWorkspaces: true },
  );
  const second = await collectCumulativeUsage(
    { workspaceId: "wks_two", agentIds: ["agent-b"] },
    paseoFor(snapshots),
    { codexHome: root, allWorkspaces: true },
  );
  assert.deepEqual(first, {
    workspaceId: WS,
    inputTokens: 100,
    cachedInputTokens: 90,
    covered: 1,
    eligible: 1,
    missing: 0,
    unavailable: 0,
    rate: 0.9,
    error: null,
  });
  assert.deepEqual(second, {
    workspaceId: "wks_two",
    inputTokens: 400,
    cachedInputTokens: 100,
    covered: 1,
    eligible: 1,
    missing: 0,
    unavailable: 0,
    rate: 0.25,
    error: null,
  });
});

test("allWorkspaces still rejects agents from another workspace and background agents", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const a = uuid(1);
  const b = uuid(2);
  await writeSession(root, a, [token(100, 50)]);
  await writeSession(root, b, [token(900, 800)]);
  const result = await collectCumulativeUsage(
    { workspaceId: WS, agentIds: ["agent-a", "agent-b", "agent-bg"] },
    paseoFor([
      snapshot("agent-a", a),
      snapshot("agent-b", b, { workspaceId: "wks_two" }),
      snapshot("agent-bg", b, { background: true }),
    ]),
    { codexHome: root, allWorkspaces: true },
  );
  assert.equal(result.covered, 1);
  assert.equal(result.eligible, 1);
  assert.equal(result.unavailable, 2);
  assert.equal(result.inputTokens, 100);
  assert.equal(result.cachedInputTokens, 50);
});

test("scope reports all mode and keeps the old empty default closed", async () => {
  const open = await workspaceScope(settingsFor({ allWorkspaces: true }));
  assert.equal(open.allWorkspaces, true);
  assert.equal(open.enabled, true);
  assert.equal(open.error, null);
  const closed = await workspaceScope(settingsFor({}));
  assert.equal(closed.enabled, false);
  assert.equal(closed.allWorkspaces, false);
  assert.equal(closed.error, null);
});

test("the explicit switch stops reads even when the old allowlist remains", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  let refreshes = 0;
  const paseo = {
    agents: {
      ref() {
        refreshes += 1;
        return { refresh: async () => snapshot("agent-a", uuid(1)) };
      },
    },
  };
  const result = await collectCumulativeUsage(
    { workspaceId: WS, agentIds: ["agent-a"] },
    paseo,
    { codexHome: root, cumulativeEnabled: false, allWorkspaces: true, workspaceIds: [WS] },
  );
  assert.equal(result.error, "累计统计未启用");
  assert.equal(result.eligible, 0);
  assert.equal(refreshes, 0);
});

test("legacy settings stay enabled, and a fresh document stays off", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const legacy = await collectCumulativeUsage(
    { workspaceId: WS, agentIds: ["agent-a"] },
    paseoFor([snapshot("agent-a", uuid(1))]),
    { codexHome: root, settings: settingsFor({ workspaceIds: [WS] }) },
  );
  assert.equal(legacy.error, null);
  assert.equal(legacy.eligible, 1);
  const fresh = await collectCumulativeUsage(
    { workspaceId: WS, agentIds: ["agent-a"] },
    paseoFor([snapshot("agent-a", uuid(1))]),
    { codexHome: root, settings: settingsFor({}) },
  );
  assert.equal(fresh.error, "累计统计未启用");
});

test("the settings stream survives until release and unsubscribes once", async () => {
  let listener;
  let unsubscribed = 0;
  const settings = {
    read: async () => ({ status: "ready", values: { allWorkspaces: true } }),
    subscribe(fn) {
      listener = fn;
      return () => { unsubscribed += 1; };
    },
  };
  const controller = new AbortController();
  const events = [];
  let settled = false;
  const pending = createScopeSubscriptionHandler(settings)({}, {
    push: async (event) => { events.push(event); },
    signal: controller.signal,
  }).then(() => { settled = true; });
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(settled, false);
  assert.equal(events.length, 1);
  assert.equal(events[0].allWorkspaces, true);
  await listener();
  assert.equal(events.length, 2);
  controller.abort();
  await pending;
  assert.equal(settled, true);
  assert.equal(unsubscribed, 1);
});

test("an older in-flight result cannot repopulate the cache after a settings change", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const first = uuid(1);
  const second = uuid(2);
  await writeSession(root, first, [token(100, 10)]);
  await writeSession(root, second, [token(200, 150)]);
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const slow = {
    agents: {
      ref() {
        return { refresh: async () => { await gate; return snapshot("agent-a", first); } };
      },
    },
  };
  const options = { codexHome: root, allWorkspaces: true };
  const oldRequest = collectCumulativeUsage(
    { workspaceId: WS, agentIds: ["agent-a"] },
    slow,
    options,
  );
  await new Promise((resolve) => setTimeout(resolve, 0));
  clearCumulativeCaches();
  const fresh = await collectCumulativeUsage(
    { workspaceId: WS, agentIds: ["agent-a"] },
    paseoFor([snapshot("agent-a", second)]),
    options,
  );
  assert.equal(fresh.inputTokens, 200);
  release();
  await oldRequest;
  const cached = await collectCumulativeUsage(
    { workspaceId: WS, agentIds: ["agent-a"] },
    paseoFor([snapshot("agent-a", second)]),
    options,
  );
  assert.equal(cached.inputTokens, 200);
  assert.equal(cached.cachedInputTokens, 150);
});

test("the latest completed Codex turn uses its own native boundaries", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const a = uuid(1);
  await writeSession(root, a, [
    tokenAt(0, 0, 0, 0),
    turnStarted("turn-1", 1),
    tokenAt(2, 1_000, 900, 120),
    tokenAt(3, 1_200, 1_050, 400),
    turnComplete("turn-1", 4),
    turnStarted("turn-2", 5),
    tokenAt(6, 1_500, 1_300, 650),
    turnComplete("turn-2", 7),
  ]);
  const result = await runTurn(root, [snapshot("agent-a", a)]);
  assert.deepEqual(result, { outputTokens: 250, elapsedMs: 2_000, firstTokenMs: null, reason: null });
});

test("a first turn has no baseline without an earlier completed boundary", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const a = uuid(1);
  await writeSession(root, a, [
    tokenAt(0, 0, 0, 0),
    turnStarted("turn-1", 1),
    tokenAt(2, 1_000, 900, 40),
    turnComplete("turn-1", 3, { time_to_first_token_ms: 850 }),
  ]);
  const result = await runTurn(root, [snapshot("agent-a", a)]);
  assert.deepEqual(result, {
    outputTokens: null,
    elapsedMs: 2_000,
    firstTokenMs: 850,
    reason: "missing-samples",
  });
});

test("a turn with invalid output in the previous turn does not reuse its baseline", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const a = uuid(1);
  await writeSession(root, a, [
    tokenAt(0, 100, 50, 100),
    turnStarted("turn-1", 1),
    turnComplete("turn-1", 2),
    turnStarted("turn-2", 3),
    tokenAt(4, 200, 100, 250),
    turnComplete("turn-2", 5),
  ]);
  const result = await runTurn(root, [snapshot("agent-a", a)]);
  assert.deepEqual(result, {
    outputTokens: null,
    elapsedMs: 2_000,
    firstTokenMs: null,
    reason: "missing-samples",
  });
});

test("a snapshot that moves backwards in time disqualifies the turn", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const a = uuid(1);
  await writeSession(root, a, [
    tokenAt(0, 0, 0, 0),
    turnStarted("turn-1", 4),
    tokenAt(3, 100, 50, 40),
    tokenAt(5, 120, 60, 80),
    turnComplete("turn-1", 6),
  ]);
  const result = await runTurn(root, [snapshot("agent-a", a)]);
  assert.equal(result.outputTokens, null);
  assert.equal(result.elapsedMs, 2_000);
});

test("a second completed turn uses the counter observed at its own start", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const a = uuid(1);
  await writeSession(root, a, [
    turnStarted("turn-1", 1),
    tokenAt(2, 100, 50, 400),
    turnComplete("turn-1", 3),
    turnStarted("turn-2", 4),
    tokenAt(5, 200, 100, 650),
    turnComplete("turn-2", 6),
  ]);
  const result = await runTurn(root, [snapshot("agent-a", a)]);
  assert.deepEqual(result, { outputTokens: 250, elapsedMs: 2_000, firstTokenMs: null, reason: null });
});

test("a turn without a completion boundary is not reported", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const a = uuid(1);
  await writeSession(root, a, [
    turnStarted("turn-1", 1),
    tokenAt(2, 100, 50, 40),
  ]);
  const result = await runTurn(root, [snapshot("agent-a", a)]);
  assert.deepEqual(result, { outputTokens: null, elapsedMs: null, firstTokenMs: null, reason: "missing-samples" });
});

test("a completion without a matching start is ignored", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const a = uuid(1);
  await writeSession(root, a, [
    tokenAt(1, 100, 50, 40),
    turnComplete("unknown", 2),
  ]);
  const result = await runTurn(root, [snapshot("agent-a", a)]);
  assert.equal(result.reason, "missing-samples");
});

test("an in-turn regression is discarded even when the final value recovers", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const a = uuid(1);
  await writeSession(root, a, [
    tokenAt(0, 0, 0, 0),
    turnStarted("turn-1", 1),
    tokenAt(2, 100, 50, 400),
    turnComplete("turn-1", 3),
    turnStarted("turn-2", 4),
    tokenAt(5, 200, 100, 300),
    tokenAt(6, 220, 110, 500),
    turnComplete("turn-2", 7),
  ]);
  const result = await runTurn(root, [snapshot("agent-a", a)]);
  assert.deepEqual(result, {
    outputTokens: null,
    elapsedMs: 3_000,
    firstTokenMs: null,
    reason: "missing-samples",
  });
});

test("Codex's own time_to_first_token_ms is projected when present", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const a = uuid(1);
  await writeSession(root, a, [
    tokenAt(0, 0, 0, 0),
    turnStarted("turn-1", 1),
    tokenAt(2, 100, 50, 40),
    turnComplete("turn-1", 3, { time_to_first_token_ms: 850 }),
  ]);
  const result = await runTurn(root, [snapshot("agent-a", a)]);
  // turn-1 is the first boundary, so it only establishes the trusted final
  // count; turn-2 then measures the delta from it.
  assert.deepEqual(result, { outputTokens: null, elapsedMs: 2_000, firstTokenMs: 850, reason: "missing-samples" });
});

test("a task_complete carrying an error is not a completed turn", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const a = uuid(1);
  await writeSession(root, a, [
    turnStarted("turn-1", 1),
    tokenAt(2, 100, 50, 40),
    turnComplete("turn-1", 3, { error: "stream disconnected" }),
  ]);
  const result = await runTurn(root, [snapshot("agent-a", a)]);
  assert.equal(result.reason, "missing-samples");
  assert.equal(result.outputTokens, null);
});

test("turn_aborted and thread_rolled_back leave no measurement", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const a = uuid(1);
  await writeSession(root, a, [
    turnStarted("turn-1", 1),
    tokenAt(2, 100, 50, 40),
    turnComplete("turn-1", 3),
    turnStarted("turn-2", 4),
    tokenAt(5, 200, 100, 80),
    turnEvent("turn_aborted", 6),
  ]);
  assert.equal((await runTurn(root, [snapshot("agent-a", a)])).reason, "missing-samples");
  clearCumulativeCaches();
  await writeSession(root, a, [
    turnStarted("turn-1", 1),
    tokenAt(2, 100, 50, 40),
    turnComplete("turn-1", 3),
    turnEvent("thread_rolled_back", 4),
  ]);
  assert.equal((await runTurn(root, [snapshot("agent-a", a)])).reason, "missing-samples");
});

test("a later turn without an observed baseline is not a delta", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const a = uuid(1);
  await writeSession(root, a, [
    turnStarted("turn-1", 1),
    turnComplete("turn-1", 2),
    turnStarted("turn-2", 3),
    tokenAt(4, 100, 50, 40),
    turnComplete("turn-2", 5),
  ]);
  const result = await runTurn(root, [snapshot("agent-a", a)]);
  assert.equal(result.reason, "missing-samples");
  assert.equal(result.outputTokens, null);
  assert.equal(result.elapsedMs, 2_000);
});

test("turn output stays gated by the cumulative switch and Codex marker", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const a = uuid(1);
  await writeSession(root, a, [
    turnStarted("turn-1", 1),
    tokenAt(2, 100, 50, 40),
    turnComplete("turn-1", 3),
  ]);
  const disabled = await collectTurnOutput(
    { workspaceId: WS, agentId: "agent-a" },
    paseoFor([snapshot("agent-a", a)]),
    { codexHome: root },
  );
  assert.equal(disabled.reason, "scope");
  const claude = await runTurn(root, [snapshot("agent-claude", a, {
    provider: "claude",
    persistence: { nativeHandle: a, metadata: {} },
  })]);
  assert.equal(claude.reason, "not-codex");
  const other = await runTurn(root, [snapshot("agent-a", a, { workspaceId: "wks_other" })]);
  assert.equal(other.reason, "read-failed");
});

test("manual refresh bypasses the short aggregation cache", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const a = uuid(1);
  const file = await writeSession(root, a, [token(100, 50)]);
  const first = await run(root, [snapshot("agent-a", a)]);
  assert.equal(first.inputTokens, 100);
  await new Promise((resolve) => setTimeout(resolve, 25));
  await fs.appendFile(file, token(200, 150) + "\n");
  const cached = await run(root, [snapshot("agent-a", a)]);
  assert.equal(cached.inputTokens, 100);
  const refreshed = await collectCumulativeUsage(
    { workspaceId: WS, agentIds: ["agent-a"], refresh: true },
    paseoFor([snapshot("agent-a", a)]),
    { codexHome: root, workspaceIds: [WS] },
  );
  assert.equal(refreshed.inputTokens, 200);
  assert.equal(file.endsWith(".jsonl"), true);
});

test("a refresh finds a rollout that appeared after a negative path cache", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const a = uuid(1);
  const before = await run(root, [snapshot("agent-a", a)]);
  assert.equal(before.covered, 0);
  await writeSession(root, a, [token(100, 50)]);
  const refreshed = await collectCumulativeUsage(
    { workspaceId: WS, agentIds: ["agent-a"], refresh: true },
    paseoFor([snapshot("agent-a", a)]),
    { codexHome: root, workspaceIds: [WS] },
  );
  assert.equal(refreshed.covered, 1);
  assert.equal(refreshed.inputTokens, 100);
});

test("settings changing during agent.refresh discards the old request", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const other = await makeRoot(t);
  const a = uuid(1);
  await writeSession(root, a, [token(100, 50)]);
  await writeSession(other, a, [token(400, 200)]);
  let revision = "r1";
  let values = { cumulativeEnabled: true, workspaceIds: [WS], codexHome: root };
  const settings = {
    read: async () => ({ status: "ready", revision, values }),
  };
  const paseo = {
    agents: {
      ref() {
        return {
          refresh: async () => {
            revision = "r2";
            values = { cumulativeEnabled: false, workspaceIds: [], codexHome: other };
            return { agent: snapshot("agent-a", a).agent };
          },
        };
      },
    },
  };
  const stale = await collectCumulativeUsage(
    { workspaceId: WS, agentIds: ["agent-a"] },
    paseo,
    { settings },
  );
  assert.equal(stale.inputTokens, 0);
  assert.notEqual(stale.error, null);
  const next = await collectCumulativeUsage(
    { workspaceId: WS, agentIds: ["agent-a"] },
    paseo,
    { settings },
  );
  assert.equal(next.error, "累计统计未启用");
});
