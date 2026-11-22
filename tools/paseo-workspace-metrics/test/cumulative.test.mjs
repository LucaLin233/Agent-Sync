import assert from "node:assert/strict";
import { test } from "node:test";
import { promises as fs } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { clearCumulativeCaches, clearCumulativeRequestCache, collectCumulativeUsage } from "../server/cumulative.ts";

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

async function makeRoot(t) {
  const root = await fs.mkdtemp(join(tmpdir(), "workspace-metrics-cumulative-"));
  t.after(async () => { await fs.rm(root, { recursive: true, force: true }); });
  await fs.mkdir(join(root, "sessions", "2026", "11", "22"), { recursive: true });
  await fs.mkdir(join(root, "archived_sessions"), { recursive: true });
  return root;
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
  assert.equal(result.error, "未配置 workspace 允许列表");
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
