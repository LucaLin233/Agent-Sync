import assert from "node:assert/strict";
import { test } from "node:test";
import {
  addTurn,
  averageFirstTokenMs,
  emptyTurnTotals,
  formatCacheRate,
  formatPillLabel,
  formatPillTitle,
  formatTokenSpeed,
  latestCacheSample,
  latestCompletedTurn,
  mergeTurnTotals,
  summarizeLatestSamples,
  tokensPerSecond,
  weightedTurnSpeed,
} from "../shared/metrics.ts";
import { pillTarget, pillTargetFor, projectDirectoryAgent } from "../shared/agents.ts";
import { workspaceInScope } from "../shared/scope.ts";

const sample = (input, cached) => latestCacheSample("codex", { inputTokens: input, cachedInputTokens: cached });

test("the panel's recent summary is weighted, not averaged, across conversations", () => {
  const summary = summarizeLatestSamples([sample(600, 590), sample(400, 392)]);
  assert.deepEqual(summary, { input: 1_000, cached: 982, covered: 2, rate: 0.982 });
  assert.equal(formatCacheRate(summary.rate), "98.2%");
  // One latest sample per conversation: a newer sample replaces that value.
  const updated = summarizeLatestSamples([sample(6_000, 100), sample(400, 392)]);
  assert.deepEqual(updated, { input: 6_400, cached: 492, covered: 2, rate: 0.076875 });
  assert.equal(formatCacheRate(updated.rate), "7.7%");
});

test("the panel's recent summary drops missing samples but keeps a real zero", () => {
  const missing = latestCacheSample("codex", null);
  const claude = latestCacheSample("claude", { inputTokens: 100, cachedInputTokens: 50 });
  assert.deepEqual(summarizeLatestSamples([missing, claude]),
    { input: 0, cached: 0, covered: 0, rate: null });
  assert.deepEqual(summarizeLatestSamples([sample(100, 0)]),
    { input: 100, cached: 0, covered: 1, rate: 0 });
  assert.equal(formatCacheRate(undefined), "—");
  assert.equal(formatCacheRate(null), "—");
});

test("the panel and pill share one scope policy, closed unless opted in", () => {
  assert.equal(workspaceInScope({ enabled: true, workspaceIds: ["w1"], allWorkspaces: false }, "w1"), true);
  assert.equal(workspaceInScope({ enabled: true, workspaceIds: ["w1"], allWorkspaces: false }, "w2"), false);
  assert.equal(workspaceInScope({ enabled: true, workspaceIds: [], allWorkspaces: true }, "w2"), true);
  assert.equal(workspaceInScope({ enabled: false, workspaceIds: [], allWorkspaces: true }, "w2"), false);
});

test("the pill follows live agents and drops archived, background, or detached ones", () => {
  assert.deepEqual(pillTarget({ id: "a", workspaceId: "w" }), { id: "a", workspaceId: "w" });
  assert.equal(pillTarget({ id: "a" }), null);
  assert.equal(pillTarget({ id: "a", workspaceId: "w", archivedAt: "2026-11-22T00:00:00Z" }), null);
  assert.equal(pillTarget({ id: "a", workspaceId: "w", background: true }), null);
  const projected = projectDirectoryAgent({ id: "b", workspaceId: "w", background: true });
  assert.equal(pillTargetFor(projected), null);
});

const turn = (completedAt, outputTokens, elapsedMs, firstTokenMs = null) => ({
  completedAt, outputTokens, elapsedMs, firstTokenMs,
});

const ready = (rate) => ({ kind: "ready", rate });
const loading = { kind: "loading" };
const off = { kind: "unavailable", reason: "累计统计已关闭" };

test("the pill shows only the cumulative rate with one decimal and a percent sign", () => {
  assert.equal(formatPillLabel(ready(0.989)), "累计 98.9%");
  assert.equal(formatPillLabel(ready(0.949)), "累计 94.9%");
  assert.equal(formatPillLabel(ready(0.9)), "累计 90.0%");
  // Real zero is a measurement, not a missing value.
  assert.equal(formatPillLabel(ready(0)), "累计 0.0%");
  // 100 is the widest reading and keeps its one decimal like the panel.
  assert.equal(formatPillLabel(ready(1)), "累计 100.0%");
  // Ordinary spaces only: no narrow or full no-break space, no percent
  // stripping, and no recent or speed field on the button.
  for (const label of [formatPillLabel(ready(0.989)), formatPillLabel(loading), formatPillLabel(off)]) {
    assert.doesNotMatch(label, /t\/s|token/i);
    assert.doesNotMatch(label, /\u202F|\u00A0/);
    assert.doesNotMatch(label, /最近/);
    assert.doesNotMatch(label, /·/);
  }
});

test("a loading or unavailable cumulative read keeps its own placeholder", () => {
  assert.equal(formatPillLabel(loading), "累计 …");
  assert.equal(formatPillLabel(off), "累计 —");
  assert.equal(formatPillLabel({ kind: "unavailable", reason: "累计读取失败" }), "累计 —");
  // A finished read without a valid snapshot is missing, never zero and never the recent sample.
  assert.equal(formatPillLabel(ready(null)), "累计 —");
});

test("the pill title names the cumulative base and explains a missing rate", () => {
  assert.equal(formatPillTitle(ready(0.949)),
    "打开工作区用量 · 累计缓存 94.9%");
  assert.equal(formatPillTitle(ready(1)),
    "打开工作区用量 · 累计缓存 100.0%");
  // Real zero prints as a value in the title too.
  assert.equal(formatPillTitle(ready(0)),
    "打开工作区用量 · 累计缓存 0.0%");
  assert.equal(formatPillTitle(off),
    "打开工作区用量 · 累计缓存 —（累计统计已关闭）");
  assert.equal(formatPillTitle({ kind: "unavailable", reason: "不在本机累计名单" }),
    "打开工作区用量 · 累计缓存 —（不在本机累计名单）");
  assert.equal(formatPillTitle({ kind: "unavailable", reason: "累计读取失败：累计用量读取失败" }),
    "打开工作区用量 · 累计缓存 —（累计读取失败：累计用量读取失败）");
  assert.equal(formatPillTitle(loading),
    "打开工作区用量 · 累计缓存 …");
  // A finished cumulative read with no valid snapshot says so instead of showing a number.
  assert.equal(formatPillTitle(ready(null)),
    "打开工作区用量 · 累计缓存 —（尚无有效累计快照）");
  // The recent sample is not part of the button title any more.
  for (const title of [formatPillTitle(ready(0.9)), formatPillTitle(off)]) {
    assert.doesNotMatch(title, /最近/);
  }
});

test("the widest labels stay inside the 160 px style bound", () => {
  // Paseo v0.17.4 public styles: 160 max width minus 12 + 12 padding, an 8 gap
  // and the 16 px icon leave 112 px for the single-line label. At the host's
  // 12 px label size "累计 100.0%" is about 2 CJK glyphs plus 6 latin ones,
  // roughly 65 px. This is a style-bound estimate, not a real layout result.
  const PILL_TEXT_BUDGET = 160 - 12 - 12 - 8 - 16; // 112 px
  const estimated = (text) => [...text].reduce((sum, char) => sum + (
    char === " " ? 3.4 : char === "%" ? 7 : char === "." ? 3.4 : char.charCodeAt(0) < 0x2e80 ? 6.7 : 12
  ), 0);
  for (const label of [
    formatPillLabel(ready(0.985)),
    formatPillLabel(ready(0.999)),
    formatPillLabel(ready(1)),
    formatPillLabel(loading),
    formatPillLabel(off),
  ]) {
    assert.ok(estimated(label) <= PILL_TEXT_BUDGET,
      `${label} ≈ ${estimated(label).toFixed(1)} px > ${PILL_TEXT_BUDGET} px`);
  }
});

test("the newest completed turn wins even when it has no speed", () => {
  const fast = turn(1_000, 900, 1_000);
  const newerMissing = turn(2_000, null, 1_500);
  assert.equal(latestCompletedTurn(fast, newerMissing), newerMissing);
  assert.equal(latestCompletedTurn(newerMissing, fast), newerMissing);
  assert.equal(latestCompletedTurn(null, null), null);
});

test("the panel keeps distinct recent and cumulative speeds while the pill carries only a rate", () => {
  let totals = emptyTurnTotals();
  const recentTurn = turn(1000, 900, 1000); // 900 t/s on its own
  totals = addTurn(totals, recentTurn);
  totals = addTurn(totals, turn(2000, 10, 10_000)); // weighted down by a slow turn
  const recentSpeed = tokensPerSecond(recentTurn.outputTokens, recentTurn.elapsedMs);
  const cumulativeSpeed = weightedTurnSpeed(totals);
  assert.equal(recentSpeed, 900);
  assert.equal(cumulativeSpeed, 910_000 / 11_000);
  // The two panel readings stay visibly different…
  assert.equal(formatTokenSpeed(recentSpeed), "900.0 t/s");
  assert.equal(formatTokenSpeed(cumulativeSpeed), "82.7 t/s");
  // …and neither leaks into the composer pill, which shows only the cumulative cache rate.
  assert.equal(formatPillLabel(ready(0.949)), "累计 94.9%");
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
