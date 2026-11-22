import assert from "node:assert/strict";
import { test } from "node:test";
import { formatCachePillLabel, formatCacheRate } from "../shared/metrics.ts";
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
