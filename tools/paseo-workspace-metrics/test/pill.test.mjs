import assert from "node:assert/strict";
import { test } from "node:test";
import {
  addTurn,
  appendTurnSpeed,
  averageFirstTokenMs,
  emptyTurnTotals,
  formatCachePillLabel,
  formatCacheRate,
  formatTurnPillLabel,
  latestCompletedTurn,
  mergeTurnTotals,
  tokensPerSecond,
  weightedTurnSpeed,
} from "../shared/metrics.ts";
import { pillTargetFor, projectDirectoryAgent, workspaceCacheSummaries } from "../shared/agents.ts";
import { workspaceInScope } from "../shared/scope.ts";

const codex = (id, workspaceId, input, cached, extra = {}) => projectDirectoryAgent({
  id,
  workspaceId,
  provider: "codex",
  lastUsage: { inputTokens: input, cachedInputTokens: cached },
  ...extra,
});

test("pill rate is weighted, not averaged, across visible conversations", () => {
  const summary = workspaceCacheSummaries([
    codex("a", "w", 600, 590),
    codex("b", "w", 400, 392),
  ]).get("w");
  assert.deepEqual(summary, { input: 1_000, cached: 982, covered: 2, rate: 0.982 });
  assert.equal(formatCachePillLabel(summary.rate), "缓存 98.2%");
});

test("an input update replaces that conversation's previous sample", () => {
  const live = new Map();
  live.set("a", codex("a", "w", 600, 590));
  live.set("b", codex("b", "w", 400, 392));
  live.set("a", codex("a", "w", 6_000, 100));
  const summary = workspaceCacheSummaries(live.values()).get("w");
  assert.deepEqual(summary, { input: 6_400, cached: 492, covered: 2, rate: 0.076875 });
  assert.equal(formatCachePillLabel(summary.rate), "缓存 7.7%");
});

test("archived conversations leave the pill total and lose their pill", () => {
  const archived = codex("b", "w", 400, 392, { archivedAt: "2026-11-22T00:00:00Z" });
  const summary = workspaceCacheSummaries([codex("a", "w", 600, 590), archived]).get("w");
  assert.deepEqual(summary, { input: 600, cached: 590, covered: 1, rate: 0.9833333333333333 });
  assert.equal(formatCachePillLabel(summary.rate), "缓存 98.3%");
  assert.equal(pillTargetFor(archived), null);
});

test("missing or non-Codex samples show no rate instead of zero", () => {
  const missing = projectDirectoryAgent({ id: "a", workspaceId: "w", provider: "codex" });
  const claude = projectDirectoryAgent({
    id: "b", workspaceId: "w", provider: "claude",
    lastUsage: { inputTokens: 100, cachedInputTokens: 50 },
  });
  assert.equal(workspaceCacheSummaries([missing, claude]).get("w"), undefined);
  assert.equal(formatCachePillLabel(undefined), "缓存 —");
  assert.equal(formatCacheRate(null), "—");
});

test("workspace scope excludes other workspaces, background, and detached agents", () => {
  const summaries = workspaceCacheSummaries([
    codex("a", "w1", 100, 50),
    codex("b", "w2", 100, 80),
    codex("c", "w1", 0, 0),
    codex("d", "w1", 100, 20, { background: true }),
    projectDirectoryAgent({
      id: "e", provider: "codex",
      lastUsage: { inputTokens: 100, cachedInputTokens: 100 },
    }),
  ]);
  assert.deepEqual(summaries.get("w1"), { input: 100, cached: 50, covered: 1, rate: 0.5 });
  assert.deepEqual(summaries.get("w2"), { input: 100, cached: 80, covered: 1, rate: 0.8 });
});

test("CCHP and GDR count only with the explicit Codex marker", () => {
  const usage = { inputTokens: 100, cachedInputTokens: 40 };
  const marked = { metadata: { provider: "codex" } };
  const summaries = workspaceCacheSummaries([
    projectDirectoryAgent({ id: "a", workspaceId: "w", provider: "cchp", lastUsage: usage, persistence: marked }),
    projectDirectoryAgent({ id: "b", workspaceId: "w", provider: "gdr", lastUsage: usage, persistence: marked }),
    projectDirectoryAgent({ id: "c", workspaceId: "w", provider: "cchp", lastUsage: usage }),
    projectDirectoryAgent({ id: "d", workspaceId: "w", provider: "gdr", lastUsage: usage, persistence: { metadata: { provider: "claude" } } }),
  ]);
  assert.deepEqual(summaries.get("w"), { input: 200, cached: 80, covered: 2, rate: 0.4 });
});

test("pill and panel share one-decimal percentage formatting", () => {
  assert.equal(formatCacheRate(0.982), "98.2%");
  assert.equal(formatCacheRate(1), "100.0%");
  assert.equal(formatCacheRate(0), "0.0%");
  assert.equal(formatCachePillLabel(0.982), "缓存 98.2%");
});

test("the panel and pill share one scope policy, closed unless opted in", () => {
  assert.equal(workspaceInScope({ enabled: true, workspaceIds: ["w1"], allWorkspaces: false }, "w1"), true);
  assert.equal(workspaceInScope({ enabled: true, workspaceIds: ["w1"], allWorkspaces: false }, "w2"), false);
  assert.equal(workspaceInScope({ enabled: true, workspaceIds: [], allWorkspaces: true }, "w2"), true);
  assert.equal(workspaceInScope({ enabled: false, workspaceIds: [], allWorkspaces: true }, "w2"), false);
});

const turn = (completedAt, outputTokens, elapsedMs, firstTokenMs = null) => ({
  completedAt, outputTokens, elapsedMs, firstTokenMs,
});

test("the pill appends only an existing speed and keeps the cache label otherwise", () => {
  assert.equal(formatTurnPillLabel(22.72), "近轮 22.7 t/s");
  assert.equal(formatTurnPillLabel(null), "近轮 —");
  assert.equal(appendTurnSpeed("缓存 98.2%", 22.72), "缓存 98.2% · 近轮 22.7 t/s");
  assert.equal(appendTurnSpeed("缓存 98.2%", null), "缓存 98.2%");
  assert.equal(appendTurnSpeed("缓存 —", 0), "缓存 — · 近轮 0.0 t/s");
  assert.equal(tokensPerSecond(400, 0), null);
  assert.equal(tokensPerSecond(null, 2_000), null);
});

test("the newest completed turn wins even when it has no speed", () => {
  const fast = turn(1_000, 900, 1_000);
  const newerMissing = turn(2_000, null, 1_500);
  assert.equal(latestCompletedTurn(fast, newerMissing), newerMissing);
  assert.equal(latestCompletedTurn(newerMissing, fast), newerMissing);
  assert.equal(latestCompletedTurn(null, null), null);
});

test("cumulative speed is weighted by whole-turn duration, not averaged", () => {
  let totals = emptyTurnTotals();
  totals = addTurn(totals, turn(1_000, 1_000, 1_000, 200)); // 1000 t/s
  totals = addTurn(totals, turn(2_000, 10, 10_000, null)); // 1 t/s
  assert.equal(totals.completed, 2);
  assert.equal(totals.speedSamples, 2);
  assert.equal(weightedTurnSpeed(totals), 1_010_000 / 11_000);
  assert.equal(averageFirstTokenMs(totals), 200);
  assert.equal(totals.firstTokenSamples, 1);
});

test("turns without an output delta or a positive duration keep separate denominators", () => {
  let totals = emptyTurnTotals();
  totals = addTurn(totals, turn(1_000, 500, null, 300));
  totals = addTurn(totals, turn(2_000, null, 4_000, null));
  totals = addTurn(totals, turn(3_000, 100, 0, 100));
  assert.equal(totals.completed, 3);
  assert.equal(totals.speedSamples, 0);
  assert.equal(weightedTurnSpeed(totals), null);
  assert.equal(totals.elapsedMs, 0);
  assert.equal(averageFirstTokenMs(totals), 200);
  assert.equal(mergeTurnTotals(totals, totals).completed, 6);
  assert.equal(mergeTurnTotals(totals, totals).firstTokenSamples, 4);
});
