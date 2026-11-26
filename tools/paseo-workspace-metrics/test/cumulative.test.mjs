import assert from "node:assert/strict";
import { test } from "node:test";
import { promises as fs } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { claudeProjectDirName, projectClaudeLine, resolveClaudeHomeFromValues, clearCumulativeCaches, clearCumulativeRequestCache, collectCumulativeUsage, collectTurnOutput, createScopeSubscriptionHandler, projectEventLine, resolveCodexHome, workspaceScope } from "../server/cumulative.ts";

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
const tokenEventAbort = (second) => turnEvent("turn_aborted", second);
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

const zeroTurns = {
  sessions: 0, completed: 0, speedSamples: 0, firstTokenSamples: 0,
  outputTokens: 0, elapsedMs: 0, firstTokenTotalMs: 0,
};

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
    latestSamples: [],
    recentTurn: null,
    turns: zeroTurns,
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

test("sessions of an unsupported provider are not eligible", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const result = await run(root, [
    snapshot("agent-other", uuid(1), {
      provider: "opencode",
      persistence: { nativeHandle: uuid(1), metadata: { provider: "opencode" } },
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
    latestSamples: [],
    recentTurn: null,
    turns: zeroTurns,
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
    latestSamples: [],
    recentTurn: null,
    turns: zeroTurns,
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
  assert.deepEqual(result, { outputTokens: 250, elapsedMs: 2_000, firstTokenMs: null, reason: null, source: "codex" });
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
    source: "codex",
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
    source: "codex",
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
  assert.deepEqual(result, { outputTokens: 250, elapsedMs: 2_000, firstTokenMs: null, reason: null, source: "codex" });
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
  assert.deepEqual(result, { outputTokens: null, elapsedMs: null, firstTokenMs: null, reason: "missing-samples", source: "codex" });
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
    source: "codex",
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
  assert.deepEqual(result, { outputTokens: null, elapsedMs: 2_000, firstTokenMs: 850, reason: "missing-samples", source: "codex" });
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
  const unsupported = await runTurn(root, [snapshot("agent-other", a, {
    provider: "opencode",
    persistence: { nativeHandle: a, metadata: { provider: "opencode" } },
  })]);
  assert.equal(unsupported.reason, "not-codex");
  assert.equal(unsupported.source, null);
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

test("disabled or out-of-scope requests never probe the configured root", async (t) => {
  clearCumulativeCaches();
  const missing = join(tmpdir(), `workspace-metrics-absent-${Date.now()}`);
  const disabled = await collectCumulativeUsage(
    { workspaceId: WS, agentIds: ["agent-a"] },
    paseoFor([snapshot("agent-a", uuid(1))]),
    { settings: settingsFor({ cumulativeEnabled: false, workspaceIds: [WS], codexHome: missing }) },
  );
  assert.equal(disabled.error, "累计统计未启用");
  const outside = await collectCumulativeUsage(
    { workspaceId: "wks_other", agentIds: ["agent-a"] },
    paseoFor([snapshot("agent-a", uuid(1))]),
    { settings: settingsFor({ cumulativeEnabled: true, workspaceIds: [WS], codexHome: missing }) },
  );
  assert.equal(outside.error, "当前 workspace 不在本机累计用量允许范围");
});

test("the aggregation cache is keyed by the usable root", async (t) => {
  clearCumulativeCaches();
  const rootA = await makeRoot(t);
  const rootB = await makeRoot(t);
  const a = uuid(1);
  await writeSession(rootA, a, [token(100, 50)]);
  await writeSession(rootB, a, [token(400, 200)]);
  const paseo = paseoFor([snapshot("agent-a", a)]);
  const first = await collectCumulativeUsage(
    { workspaceId: WS, agentIds: ["agent-a"] },
    paseo,
    { codexHome: rootA, workspaceIds: [WS] },
  );
  assert.equal(first.inputTokens, 100);
  const second = await collectCumulativeUsage(
    { workspaceId: WS, agentIds: ["agent-a"] },
    paseo,
    { codexHome: rootB, workspaceIds: [WS] },
  );
  assert.equal(second.inputTokens, 400);
});

test("an invalid cache snapshot keeps the last valid sample", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const a = uuid(1);
  await writeSession(root, a, [
    token(100, 50),
    JSON.stringify({
      timestamp: "2026-11-22T00:00:02Z",
      type: "event_msg",
      payload: { type: "token_count", info: { total_token_usage: { input_tokens: 50, cached_input_tokens: 90, output_tokens: 10 } } },
    }),
  ]);
  const result = await run(root, [snapshot("agent-a", a)]);
  assert.equal(result.inputTokens, 100);
  assert.equal(result.cachedInputTokens, 50);
});

test("first-token timing survives a zero elapsed duration", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const a = uuid(1);
  await writeSession(root, a, [
    turnStarted("turn-1", 2),
    tokenAt(2, 100, 50, 40),
    turnComplete("turn-1", 2, { time_to_first_token_ms: 850 }),
  ]);
  const result = await runTurn(root, [snapshot("agent-a", a)]);
  assert.deepEqual(result, { outputTokens: null, elapsedMs: 0, firstTokenMs: 850, reason: "missing-samples", source: "codex" });
});

test("structural projection ignores content and nested fields while keeping the envelope type", () => {
  const line = JSON.stringify({
    timestamp: "2026-11-22T00:00:03Z",
    type: "event_msg",
    payload: {
      type: "task_complete",
      turn_id: "turn-real",
      last_agent_message: "text with \"turn_id\":\"fake\" and \"error\":{\"x\":1} and \"}\"",
      error: { detail: "nested \"time_to_first_token_ms\": 1" },
      extra: { deep: [1, { content: "\"turn_id\":\"fake2\"" }] },
      time_to_first_token_ms: 850,
    },
  });
  assert.deepEqual(projectEventLine(line), {
    eventType: "event_msg",
    payloadType: "task_complete",
    timestamp: "2026-11-22T00:00:03Z",
    turnId: "turn-real",
    firstTokenMs: 850,
    errorPresent: true,
    input: null,
    cached: null,
    output: null,
    closed: true,
  });
  const notEvent = JSON.stringify({
    type: "response_item",
    payload: { type: "task_complete", turn_id: "turn-fake", time_to_first_token_ms: 1 },
  });
  assert.equal(projectEventLine(notEvent).eventType, "response_item");
  const nestedUsage = JSON.stringify({
    timestamp: "2026-11-22T00:00:04Z",
    type: "event_msg",
    payload: {
      type: "token_count",
      info: { total_token_usage: { input_tokens: 12, cached_input_tokens: 3, output_tokens: 4 }, extra: { output_tokens: 999 } },
      text: "\"input_tokens\": 999",
    },
  });
  const usage = projectEventLine(nestedUsage);
  assert.equal(usage.input, 12);
  assert.equal(usage.cached, 3);
  assert.equal(usage.output, 4);
});

test("a between-turn counter change invalidates the next baseline", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const a = uuid(1);
  await writeSession(root, a, [
    turnStarted("turn-1", 1),
    tokenAt(2, 100, 50, 40),
    turnComplete("turn-1", 3),
    tokenAt(4, 160, 80, 60),
    turnStarted("turn-2", 5),
    tokenAt(6, 220, 110, 80),
    turnComplete("turn-2", 7),
  ]);
  const result = await runTurn(root, [snapshot("agent-a", a)]);
  assert.equal(result.outputTokens, null);
  assert.equal(result.reason, "missing-samples");
  assert.equal(result.elapsedMs, 2_000);
});

test("boundaries alone return timing on first read and on the cache hit", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const a = uuid(1);
  await writeSession(root, a, [
    turnStarted("turn-1", 1),
    turnComplete("turn-1", 3, { time_to_first_token_ms: 850 }),
  ]);
  const first = await runTurn(root, [snapshot("agent-a", a)]);
  assert.deepEqual(first, { outputTokens: null, elapsedMs: 2_000, firstTokenMs: 850, reason: "missing-samples", source: "codex" });
  const cached = await runTurn(root, [snapshot("agent-a", a)]);
  assert.deepEqual(cached, first);
});

test("missing agents are part of the aggregation cache key", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const a = uuid(1);
  await writeSession(root, a, [token(100, 50)]);
  const paseo = paseoFor([snapshot("agent-a", a)]);
  const first = await collectCumulativeUsage(
    { workspaceId: WS, agentIds: ["agent-a"] },
    paseo,
    { codexHome: root, workspaceIds: [WS] },
  );
  assert.equal(first.covered, 1);
  assert.equal(first.unavailable, 0);
  const second = await collectCumulativeUsage(
    { workspaceId: WS, agentIds: ["agent-a", "agent-missing"] },
    paseo,
    { codexHome: root, workspaceIds: [WS] },
  );
  assert.equal(second.covered, 1);
  assert.equal(second.unavailable, 1);
});

test("exponent numbers are consumed fully and truncated records are ignored", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const a = uuid(1);
  const exponent = JSON.stringify({
    timestamp: "2026-11-22T00:00:00Z",
    type: "event_msg",
    payload: {
      type: "token_count",
      info: { total_token_usage: { input_tokens: 12e2, cached_input_tokens: 0, output_tokens: 4 } },
    },
  });
  const truncated = '{"timestamp":"2026-11-22T00:00:01Z","type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":900';
  assert.equal(projectEventLine(exponent).input, 1_200);
  assert.equal(projectEventLine(truncated).closed, false);
  await writeSession(root, a, [truncated, exponent]);
  const result = await run(root, [snapshot("agent-a", a)]);
  assert.equal(result.inputTokens, 1_200);
  assert.equal(result.covered, 1);
});

test("the recent turn is chosen by completion time, not by having a speed", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const a = uuid(1);
  const b = uuid(2);
  await writeSession(root, a, [
    tokenAt(0, 0, 0, 0),
    turnStarted("turn-1", 1),
    tokenAt(2, 100, 50, 100),
    turnComplete("turn-1", 3),
    turnStarted("turn-2", 4),
    tokenAt(5, 200, 100, 900),
    turnComplete("turn-2", 6, { time_to_first_token_ms: 700 }),
  ]);
  // A second session completed earlier with a usable speed.
  await writeSession(root, b, [
    tokenAt(0, 0, 0, 0),
    turnStarted("turn-1", 1),
    tokenAt(2, 100, 50, 1_000),
    turnComplete("turn-1", 2),
    turnStarted("turn-2", 3),
    tokenAt(4, 200, 100, 1_300),
    turnComplete("turn-2", 5),
  ]);
  const result = await run(root, [snapshot("agent-a", a), snapshot("agent-b", b)]);
  // The newer turn wins even though it has no output baseline of its own.
  assert.deepEqual(result.recentTurn, {
    completedAt: Date.parse(at(6)),
    outputTokens: 800,
    elapsedMs: 2_000,
    firstTokenMs: 700,
  });
  assert.equal(result.turns.sessions, 2);
  assert.equal(result.turns.completed, 4);
  assert.equal(result.turns.speedSamples, 2);
});

test("a newer turn without a usable speed is kept over an older fast turn", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const a = uuid(1);
  const b = uuid(2);
  // Session A completes newer but reports no output counter for that turn.
  await writeSession(root, a, [
    tokenAt(0, 0, 0, 0),
    turnStarted("turn-1", 1),
    tokenAt(2, 100, 50, 400),
    turnComplete("turn-1", 3),
    turnStarted("turn-2", 4),
    turnComplete("turn-2", 6),
  ]);
  // Session B completed earlier with a usable speed.
  await writeSession(root, b, [
    tokenAt(0, 0, 0, 0),
    turnStarted("turn-1", 1),
    tokenAt(2, 100, 50, 1_000),
    turnComplete("turn-1", 2),
    turnStarted("turn-2", 3),
    tokenAt(4, 200, 100, 1_300),
    turnComplete("turn-2", 5),
  ]);
  const result = await run(root, [snapshot("agent-a", a), snapshot("agent-b", b)]);
  assert.deepEqual(result.recentTurn, {
    completedAt: Date.parse(at(6)),
    outputTokens: null,
    elapsedMs: 2_000,
    firstTokenMs: null,
  });
  assert.equal(result.turns.completed, 4);
  assert.equal(result.turns.speedSamples, 1);
});

test("cumulative turns are weighted by each whole-turn duration", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const a = uuid(1);
  const b = uuid(2);
  // Long turn: 1,000 output over 10 s. Short turn: 600 over 2 s.
  await writeSession(root, a, [
    tokenAt(0, 0, 0, 0),
    turnStarted("turn-1", 1),
    tokenAt(2, 0, 0, 0),
    turnComplete("turn-1", 2, { time_to_first_token_ms: 500 }),
    turnStarted("turn-2", 3),
    tokenAt(5, 0, 0, 1_000),
    turnComplete("turn-2", 13, { time_to_first_token_ms: 900 }),
  ]);
  await writeSession(root, b, [
    tokenAt(0, 0, 0, 0),
    turnStarted("turn-1", 1),
    tokenAt(2, 0, 0, 0),
    turnComplete("turn-1", 2),
    turnStarted("turn-2", 3),
    tokenAt(4, 0, 0, 600),
    turnComplete("turn-2", 5),
  ]);
  const result = await run(root, [snapshot("agent-a", a), snapshot("agent-b", b)]);
  assert.equal(result.turns.speedSamples, 2);
  assert.equal(result.turns.outputTokens, 1_600);
  assert.equal(result.turns.elapsedMs, 12_000);
  assert.equal(result.turns.firstTokenSamples, 2);
  assert.equal(result.turns.firstTokenTotalMs, 1_400);
  // 1,600 / 12 s = 133.3 t/s, not the unweighted mean of 100 and 300 t/s.
  const speed = result.turns.outputTokens * 1_000 / result.turns.elapsedMs;
  assert.equal(Math.round(speed * 10) / 10, 133.3);
});

test("failed, baseline-less, and out-of-scope turns never join the totals", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const failed = uuid(1);
  const noBaseline = uuid(2);
  await writeSession(root, failed, [
    turnStarted("turn-1", 1),
    tokenAt(2, 100, 50, 400),
    turnComplete("turn-1", 3, { error: "stream disconnected" }),
    turnStarted("turn-2", 4),
    tokenEventAbort(5),
  ]);
  await writeSession(root, noBaseline, [
    turnStarted("turn-1", 1),
    tokenAt(2, 100, 50, 400),
    turnComplete("turn-1", 3),
    turnStarted("turn-2", 4),
    tokenAt(5, 200, 100, 900),
    turnComplete("turn-2", 6),
  ]);
  const result = await collectCumulativeUsage(
    { workspaceId: WS, agentIds: ["agent-failed", "agent-nobase", "agent-other"] },
    paseoFor([
      snapshot("agent-failed", failed),
      snapshot("agent-nobase", noBaseline),
      snapshot("agent-other", uuid(3), { workspaceId: "wks_other" }),
    ]),
    { codexHome: root, workspaceIds: [WS] },
  );
  // The failed session contributes no turn. The no-baseline session counts
  // both completions, but only the second has an output delta and a speed.
  assert.equal(result.turns.sessions, 1);
  assert.equal(result.turns.completed, 2);
  assert.equal(result.turns.speedSamples, 1);
  assert.equal(result.turns.outputTokens, 500);
  assert.notEqual(result.unavailable, 0);
});

test("a completed turn replayed after a rollback is not counted twice", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const a = uuid(1);
  await writeSession(root, a, [
    tokenAt(0, 0, 0, 0),
    turnStarted("turn-1", 1),
    tokenAt(2, 100, 50, 400),
    turnComplete("turn-1", 3, { time_to_first_token_ms: 850 }),
    turnStarted("turn-2", 4),
    tokenAt(5, 200, 100, 900),
    turnComplete("turn-2", 6),
    turnEvent("thread_rolled_back", 7),
    turnStarted("turn-2", 8),
    tokenAt(9, 200, 100, 900),
    turnComplete("turn-2", 10),
  ]);
  const result = await run(root, [snapshot("agent-a", a)]);
  // The rollback drops the visible latest turn, but the already-observed
  // successful turn is not a second observation when replayed.
  assert.equal(result.turns.completed, 2);
  assert.equal(result.turns.speedSamples, 1);
  assert.equal(result.recentTurn, null);
  // The detail follows file order, so the replayed turn re-describes it: its
  // own boundaries are back, while the cleared baseline keeps the delta empty.
  const detail = await runTurn(root, [snapshot("agent-a", a)]);
  assert.deepEqual(detail, {
    outputTokens: null,
    elapsedMs: 2_000,
    firstTokenMs: null,
    reason: "missing-samples",
    source: "codex",
  });
});

test("the session's latest success keeps the greatest completion time", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const a = uuid(1);
  const b = uuid(2);
  await writeSession(root, a, [
    tokenAt(0, 0, 0, 0),
    turnStarted("turn-1", 1),
    tokenAt(2, 0, 0, 0),
    turnComplete("turn-1", 2),
    turnStarted("turn-2", 3),
    tokenAt(5, 0, 0, 500),
    turnComplete("turn-2", 9),
  ]);
  // B finishes at second 7, between A's two turns.
  await writeSession(root, b, [
    tokenAt(0, 0, 0, 0),
    turnStarted("turn-b1", 1),
    tokenAt(2, 0, 0, 0),
    turnComplete("turn-b1", 2),
    turnStarted("turn-b2", 3),
    tokenAt(5, 0, 0, 300),
    turnComplete("turn-b2", 7),
  ]);
  const result = await run(root, [snapshot("agent-a", a), snapshot("agent-b", b)]);
  // A's second turn (second 9) is newest even though B is read second.
  assert.equal(result.recentTurn.completedAt, Date.parse(at(9)));
  assert.equal(result.recentTurn.outputTokens, 500);
});

test("a replayed turn refreshes the detail with its own duration, still counted once", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const a = uuid(1);
  await writeSession(root, a, [
    tokenAt(0, 0, 0, 0),
    turnStarted("turn-1", 1),
    tokenAt(2, 0, 0, 0),
    turnComplete("turn-1", 3),
    turnEvent("thread_rolled_back", 4),
    turnStarted("turn-1", 7),
    tokenAt(7, 0, 0, 0),
    turnComplete("turn-1", 8),
  ]);
  const detail = await runTurn(root, [snapshot("agent-a", a)]);
  // The replayed turn is the detail's terminal measurement: 1 s, not the
  // pre-rollback 2 s it replaced.
  assert.deepEqual(detail, {
    outputTokens: null,
    elapsedMs: 1_000,
    firstTokenMs: null,
    reason: "missing-samples",
    source: "codex",
  });
  const result = await run(root, [snapshot("agent-a", a)]);
  assert.equal(result.turns.completed, 1);
  assert.equal(result.recentTurn, null);
});

test("manual refresh recomputes turns from the same incremental read", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const a = uuid(1);
  const file = await writeSession(root, a, [
    tokenAt(0, 0, 0, 0),
    turnStarted("turn-1", 1),
    tokenAt(2, 0, 0, 0),
    turnComplete("turn-1", 2),
    turnStarted("turn-2", 3),
    tokenAt(4, 0, 0, 300),
    turnComplete("turn-2", 5),
  ]);
  const first = await run(root, [snapshot("agent-a", a)]);
  assert.equal(first.turns.completed, 2);
  await fs.appendFile(file, [
    turnStarted("turn-3", 6),
    tokenAt(8, 0, 0, 700),
    turnComplete("turn-3", 10),
    "",
  ].join("\n"));
  const refreshed = await collectCumulativeUsage(
    { workspaceId: WS, agentIds: ["agent-a"], refresh: true },
    paseoFor([snapshot("agent-a", a)]),
    { codexHome: root, workspaceIds: [WS] },
  );
  assert.equal(refreshed.turns.completed, 3);
  assert.equal(refreshed.turns.outputTokens, 700);
  // turn-2 spans 2 s and turn-3 spans 4 s; the first completion has no baseline.
  assert.equal(refreshed.turns.elapsedMs, 6_000);
});

test("a successful turn survives a later failed or canceled turn for the top card", async (t) => {
  clearCumulativeCaches();
  const root = await makeRoot(t);
  const a = uuid(1);
  await writeSession(root, a, [
    tokenAt(0, 0, 0, 0),
    turnStarted("turn-1", 1),
    tokenAt(2, 100, 50, 400),
    turnComplete("turn-1", 3),
    turnStarted("turn-2", 4),
    tokenAt(5, 200, 100, 900),
    turnComplete("turn-2", 6),
    turnStarted("turn-3", 7),
    tokenEventAbort(8),
  ]);
  const aborted = await run(root, [snapshot("agent-a", a)]);
  assert.deepEqual(aborted.recentTurn, {
    completedAt: Date.parse(at(6)),
    outputTokens: 500,
    elapsedMs: 2_000,
    firstTokenMs: null,
  });
  assert.equal(aborted.turns.completed, 2);

  clearCumulativeCaches();
  await writeSession(root, a, [
    tokenAt(0, 0, 0, 0),
    turnStarted("turn-1", 1),
    tokenAt(2, 100, 50, 400),
    turnComplete("turn-1", 3),
    turnStarted("turn-2", 4),
    tokenAt(5, 200, 100, 900),
    turnComplete("turn-2", 6),
    turnStarted("turn-3", 7),
    turnComplete("turn-3", 8, { error: "stream disconnected" }),
  ]);
  const failed = await run(root, [snapshot("agent-a", a)]);
  assert.equal(failed.recentTurn.completedAt, Date.parse(at(6)));
  assert.equal(failed.recentTurn.outputTokens, 500);
});

// --- Claude Code transcripts -------------------------------------------------

const claudeAssistant = (id, input, creation, read, output = 1, content = "secret text") => JSON.stringify({
  type: "assistant",
  sessionId: "ignored",
  timestamp: "2026-11-22T00:00:00Z",
  message: {
    id,
    type: "message",
    role: "assistant",
    content: [{ type: "text", text: content, usage: { input_tokens: 999999 } }],
    usage: {
      input_tokens: input,
      cache_creation_input_tokens: creation,
      cache_read_input_tokens: read,
      output_tokens: output,
      iterations: [{ input_tokens: 777777, cache_read_input_tokens: 777777 }],
    },
  },
});

async function makeClaudeRoot(t) {
  const root = await fs.mkdtemp(join(tmpdir(), "workspace-metrics-claude-"));
  t.after(async () => { await fs.rm(root, { recursive: true, force: true }); });
  await fs.mkdir(join(root, "projects"), { recursive: true });
  return root;
}

async function writeClaude(root, project, id, lines) {
  await fs.mkdir(join(root, "projects", project), { recursive: true });
  const file = join(root, "projects", project, `${id}.jsonl`);
  await fs.writeFile(file, lines.join("\n") + "\n");
  return file;
}

function claudeSnapshot(id, nativeHandle, overrides = {}) {
  return snapshot(id, nativeHandle, {
    provider: "claude-cchp",
    cwd: "/nonexistent/project",
    persistence: { nativeHandle, metadata: { provider: "claude" } },
    ...overrides,
  });
}

async function runClaude(claudeRoot, snapshots, codexRoot) {
  return collectCumulativeUsage(
    { workspaceId: WS, agentIds: snapshots.map(({ agent }) => agent.id) },
    paseoFor(snapshots),
    { codexHome: codexRoot, claudeHome: claudeRoot, workspaceIds: [WS] },
  );
}

test("Claude sessions sum each request once; cache writes and reads join the input", async (t) => {
  clearCumulativeCaches();
  const root = await makeClaudeRoot(t);
  const id = uuid(41);
  await writeClaude(root, claudeProjectDirName("/nonexistent/project"), id, [
    JSON.stringify({ type: "user", message: { role: "user", content: "hi" } }),
    claudeAssistant("msg_1", 2, 1000, 0),
    // The same message split into another content block repeats its usage.
    claudeAssistant("msg_1", 2, 1000, 0),
    claudeAssistant("msg_2", 3, 100, 1000),
    JSON.stringify({ type: "system", subtype: "x" }),
  ]);
  const result = await runClaude(root, [claudeSnapshot("agent-c", id)]);
  assert.equal(result.error, null);
  assert.equal(result.eligible, 1);
  assert.equal(result.covered, 1);
  assert.equal(result.inputTokens, 2 + 1000 + 3 + 100 + 1000);
  assert.equal(result.cachedInputTokens, 1000);
  assert.equal(result.rate, 1000 / 2105);
});

test("a Claude session resumed under another project directory is still found", async (t) => {
  clearCumulativeCaches();
  const root = await makeClaudeRoot(t);
  const id = uuid(42);
  await writeClaude(root, "-some-other-path", id, [claudeAssistant("msg_1", 10, 0, 90)]);
  const result = await runClaude(root, [claudeSnapshot("agent-c", id)]);
  assert.equal(result.covered, 1);
  assert.equal(result.rate, 0.9);
});

test("Codex and Claude sessions in one workspace are weighted together", async (t) => {
  clearCumulativeCaches();
  const codexRoot = await makeRoot(t);
  const claudeRoot = await makeClaudeRoot(t);
  const codexId = uuid(43);
  const claudeId = uuid(44);
  await writeSession(codexRoot, codexId, [token(100, 50)]);
  await writeClaude(claudeRoot, "-p", claudeId, [claudeAssistant("msg_1", 0, 0, 100)]);
  const result = await runClaude(claudeRoot, [
    snapshot("agent-x", codexId),
    claudeSnapshot("agent-c", claudeId),
  ], codexRoot);
  assert.equal(result.eligible, 2);
  assert.equal(result.covered, 2);
  assert.equal(result.inputTokens, 200);
  assert.equal(result.cachedInputTokens, 150);
});

test("a missing Claude root leaves Claude sessions missing without hiding Codex", async (t) => {
  clearCumulativeCaches();
  const codexRoot = await makeRoot(t);
  const codexId = uuid(45);
  await writeSession(codexRoot, codexId, [token(100, 50)]);
  const result = await collectCumulativeUsage(
    { workspaceId: WS, agentIds: ["agent-x", "agent-c"] },
    paseoFor([snapshot("agent-x", codexId), claudeSnapshot("agent-c", uuid(46))]),
    { codexHome: codexRoot, claudeHome: join(tmpdir(), `missing-claude-${Date.now()}`), workspaceIds: [WS] },
  );
  assert.equal(result.error, null);
  assert.equal(result.eligible, 2);
  assert.equal(result.covered, 1);
  assert.equal(result.missing, 1);
  assert.equal(result.rate, 0.5);
});

test("a Claude transcript without usage stays missing, and appends are read incrementally", async (t) => {
  clearCumulativeCaches();
  const root = await makeClaudeRoot(t);
  const id = uuid(47);
  const file = await writeClaude(root, "-p", id, [JSON.stringify({ type: "user", message: { content: "x" } })]);
  const snaps = [claudeSnapshot("agent-c", id)];
  let result = await runClaude(root, snaps);
  assert.equal(result.covered, 0);
  assert.equal(result.missing, 1);
  assert.equal(result.rate, null);
  await fs.appendFile(file, claudeAssistant("msg_1", 0, 50, 50) + "\n");
  clearCumulativeRequestCache();
  result = await runClaude(root, snaps);
  assert.equal(result.covered, 1);
  assert.equal(result.inputTokens, 100);
  await fs.appendFile(file, claudeAssistant("msg_1", 0, 50, 50) + "\n" + claudeAssistant("msg_2", 0, 0, 100) + "\n");
  clearCumulativeRequestCache();
  result = await runClaude(root, snaps);
  assert.equal(result.inputTokens, 200);
  assert.equal(result.cachedInputTokens, 150);
});

test("symlinked Claude transcripts are skipped", async (t) => {
  clearCumulativeCaches();
  const root = await makeClaudeRoot(t);
  const id = uuid(48);
  const real = await writeClaude(root, "-real", "elsewhere", [claudeAssistant("msg_1", 0, 0, 10)]);
  await fs.mkdir(join(root, "projects", "-p"), { recursive: true });
  await fs.symlink(real, join(root, "projects", "-p", `${id}.jsonl`));
  const result = await runClaude(root, [claudeSnapshot("agent-c", id)]);
  assert.equal(result.covered, 0);
});

test("Claude projection keeps only envelope fields, block types and top-level usage", () => {
  const projected = projectClaudeLine(claudeAssistant("msg_9", 1, 2, 3));
  assert.deepEqual(projected, {
    eventType: "assistant", timestamp: "2026-11-22T00:00:00Z", uuid: null,
    sidechain: false, meta: false, apiError: false,
    messageId: "msg_9", stopReason: null, contentTypes: ["text"],
    input: 1, cacheCreation: 2, cacheRead: 3, output: 1, closed: true,
  });
  assert.equal(projectClaudeLine(claudeAssistant("msg_9", 1, 2, 3).slice(0, -2)).closed, false);
});

test("Claude home: manual setting inside home, CLAUDE_CONFIG_DIR, then ~/.claude", async (t) => {
  const { base, home } = await makeHome(t);
  assert.notEqual((await resolveClaudeHomeFromValues({}, { home, env: null })).error, null);
  await fs.mkdir(join(home, ".claude", "projects"), { recursive: true });
  assert.equal((await resolveClaudeHomeFromValues({}, { home, env: null })).root, join(home, ".claude"));
  const external = join(base, "claude-config");
  await fs.mkdir(join(external, "projects"), { recursive: true });
  assert.equal((await resolveClaudeHomeFromValues({}, { home, env: external })).root, external);
  const manual = join(home, "alt-claude");
  await fs.mkdir(join(manual, "projects"), { recursive: true });
  assert.equal((await resolveClaudeHomeFromValues({ claudeHome: manual }, { home, env: external })).root, manual);
  // A manual value outside home or relative fails without falling back.
  const outside = await resolveClaudeHomeFromValues({ claudeHome: external }, { home, env: null });
  assert.equal(outside.root, null);
  assert.notEqual(outside.error, null);
  assert.equal((await resolveClaudeHomeFromValues({ claudeHome: "rel" }, { home, env: null })).root, null);
});

// --- Claude turns and latest samples -----------------------------------------

const cAt = (second) => `2026-11-22T00:01:${String(second).padStart(2, "0")}Z`;
const cPrompt = (uuid, second, extra = {}) => JSON.stringify({
  type: "user", uuid, timestamp: cAt(second), isSidechain: false,
  message: { role: "user", content: "do something" }, ...extra,
});
const cToolResult = (second) => JSON.stringify({
  type: "user", uuid: `tr-${second}`, timestamp: cAt(second),
  message: { role: "user", content: [{ type: "tool_result", tool_use_id: "x", content: "out" }] },
});
const cReply = (id, second, { stop = "tool_use", input = 2, creation = 0, read = 100, output = 50, block = "text", extra = {} } = {}) => JSON.stringify({
  type: "assistant", uuid: `a-${id}-${second}`, timestamp: cAt(second), isSidechain: false,
  message: {
    id, role: "assistant", stop_reason: stop,
    content: [{ type: block, text: "hidden" }],
    usage: { input_tokens: input, cache_creation_input_tokens: creation, cache_read_input_tokens: read, output_tokens: output },
  },
  ...extra,
});

async function claudeTurnFor(root, id) {
  return collectTurnOutput(
    { workspaceId: WS, agentId: "agent-c" },
    paseoFor([claudeSnapshot("agent-c", id)]),
    { claudeHome: root, workspaceIds: [WS] },
  );
}

test("a Claude turn runs from the prompt to the last record of its end_turn message", async (t) => {
  clearCumulativeCaches();
  const root = await makeClaudeRoot(t);
  const id = uuid(51);
  await writeClaude(root, "-p", id, [
    cPrompt("p1", 0),
    cReply("m1", 2, { block: "thinking", output: 30 }),
    cReply("m1", 3, { output: 30 }),
    cToolResult(4),
    cReply("m2", 6, { stop: "end_turn", block: "thinking", output: 70 }),
    cReply("m2", 9, { stop: "end_turn", output: 70 }),
  ]);
  const turn = await claudeTurnFor(root, id);
  assert.deepEqual(turn, { outputTokens: 100, elapsedMs: 9_000, firstTokenMs: null, reason: null, source: "claude" });
  const result = await runClaude(root, [claudeSnapshot("agent-c", id)]);
  assert.deepEqual(result.recentTurn, { completedAt: Date.parse(cAt(9)), outputTokens: 100, elapsedMs: 9_000, firstTokenMs: null });
  assert.equal(result.turns.completed, 1);
  assert.equal(result.turns.speedSamples, 1);
  assert.equal(result.turns.outputTokens, 100);
  assert.equal(result.turns.elapsedMs, 9_000);
  assert.equal(result.turns.sessions, 1);
  assert.deepEqual(result.latestSamples, [{ agentId: "agent-c", input: 102, cached: 100 }]);
});

test("a pending Claude turn is counted once across reads and when the next prompt closes it", async (t) => {
  clearCumulativeCaches();
  const root = await makeClaudeRoot(t);
  const id = uuid(52);
  const file = await writeClaude(root, "-p", id, [cPrompt("p1", 0), cReply("m1", 4, { stop: "end_turn", output: 40 })]);
  const snaps = [claudeSnapshot("agent-c", id)];
  let result = await runClaude(root, snaps);
  assert.equal(result.turns.completed, 1);
  clearCumulativeRequestCache();
  result = await runClaude(root, snaps);
  assert.equal(result.turns.completed, 1);
  await fs.appendFile(file, [cPrompt("p2", 10), cReply("m2", 12, { stop: "end_turn", output: 20 })].join("\n") + "\n");
  clearCumulativeRequestCache();
  result = await runClaude(root, snaps);
  assert.equal(result.turns.completed, 2);
  assert.equal(result.turns.outputTokens, 60);
  assert.equal(result.turns.elapsedMs, 6_000);
  assert.equal(result.recentTurn.completedAt, Date.parse(cAt(12)));
});

test("a request after end_turn continues the Claude turn instead of closing it", async (t) => {
  clearCumulativeCaches();
  const root = await makeClaudeRoot(t);
  const id = uuid(53);
  await writeClaude(root, "-p", id, [
    cPrompt("p1", 0),
    cReply("m1", 2, { stop: "end_turn", output: 10 }),
    cReply("m2", 5, { stop: "end_turn", output: 15 }),
  ]);
  const turn = await claudeTurnFor(root, id);
  assert.equal(turn.outputTokens, 25);
  assert.equal(turn.elapsedMs, 5_000);
  const result = await runClaude(root, [claudeSnapshot("agent-c", id)]);
  assert.equal(result.turns.completed, 1);
});

test("abandoned, failed and sidechain Claude work is never a completed turn", async (t) => {
  clearCumulativeCaches();
  const root = await makeClaudeRoot(t);
  const id = uuid(54);
  await writeClaude(root, "-p", id, [
    cPrompt("p1", 0),
    cReply("m1", 2, { output: 10 }),
    // A new prompt before end_turn abandons p1.
    cPrompt("p2", 3),
    cReply("m2", 4, { output: 10 }),
    JSON.stringify({ type: "assistant", timestamp: cAt(5), isApiErrorMessage: true, message: { id: "e1", stop_reason: "stop_sequence", content: [], usage: { input_tokens: 0, output_tokens: 0 } } }),
    cPrompt("s1", 6, { isSidechain: true }),
    cReply("s2", 7, { stop: "end_turn", extra: { isSidechain: true } }),
    cPrompt("meta", 8, { isMeta: true }),
  ]);
  const result = await runClaude(root, [claudeSnapshot("agent-c", id)]);
  assert.equal(result.turns.completed, 0);
  assert.equal(result.recentTurn, null);
  // Sidechain requests still count for cache, but not as the latest main-chain sample.
  assert.equal(result.inputTokens, 102 * 3);
  assert.deepEqual(result.latestSamples, [{ agentId: "agent-c", input: 102, cached: 100 }]);
  const turn = await claudeTurnFor(root, id);
  assert.equal(turn.reason, "missing-samples");
  assert.equal(turn.source, "claude");
});

test("the latest Claude sample is the newest main-chain request, deduplicated per session", async (t) => {
  clearCumulativeCaches();
  const root = await makeClaudeRoot(t);
  const id = uuid(55);
  await writeClaude(root, "-p", id, [
    cPrompt("p1", 0),
    cReply("m1", 1, { input: 5, creation: 500, read: 0 }),
    cReply("m2", 2, { input: 1, creation: 9, read: 90, stop: "end_turn" }),
  ]);
  const result = await collectCumulativeUsage(
    { workspaceId: WS, agentIds: ["agent-c", "agent-d"] },
    paseoFor([claudeSnapshot("agent-c", id), claudeSnapshot("agent-d", id)]),
    { claudeHome: root, workspaceIds: [WS] },
  );
  assert.equal(result.eligible, 1);
  assert.deepEqual(result.latestSamples, [{ agentId: "agent-c", input: 100, cached: 90 }]);
});
