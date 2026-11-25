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
  formatTokenSpeedNumber,
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
  assert.equal(formatCacheRate(summary.rate), "98.2%");
});

test("an input update replaces that conversation's previous sample", () => {
  const live = new Map();
  live.set("a", codex("a", "w", 600, 590));
  live.set("b", codex("b", "w", 400, 392));
  live.set("a", codex("a", "w", 6_000, 100));
  const summary = workspaceCacheSummaries(live.values()).get("w");
  assert.deepEqual(summary, { input: 6_400, cached: 492, covered: 2, rate: 0.076875 });
  assert.equal(formatCacheRate(summary.rate), "7.7%");
});

test("archived conversations leave the pill total and lose their pill", () => {
  const archived = codex("b", "w", 400, 392, { archivedAt: "2026-11-22T00:00:00Z" });
  const summary = workspaceCacheSummaries([codex("a", "w", 600, 590), archived]).get("w");
  assert.deepEqual(summary, { input: 600, cached: 590, covered: 1, rate: 0.9833333333333333 });
  assert.equal(formatCacheRate(summary.rate), "98.3%");
  assert.equal(pillTargetFor(archived), null);
});

test("missing or non-Codex samples show no rate instead of zero", () => {
  const missing = projectDirectoryAgent({ id: "a", workspaceId: "w", provider: "codex" });
  const claude = projectDirectoryAgent({
    id: "b", workspaceId: "w", provider: "claude",
    lastUsage: { inputTokens: 100, cachedInputTokens: 50 },
  });
  assert.equal(workspaceCacheSummaries([missing, claude]).get("w"), undefined);
  assert.equal(formatCacheRate(undefined), "—");
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

const ready = (rate) => ({ kind: "ready", rate });
const loading = { kind: "loading" };
const off = { kind: "unavailable", reason: "累计统计已关闭" };

const LABEL_SEP = "\u202F";

test("the pill keeps both readings, drops the percent sign and never a speed", () => {
  // The two slots are independent readings, so different numbers both show.
  assert.equal(formatPillLabel(ready(0.949), ready(0.812)),
    "累计" + LABEL_SEP + "94.9 · 最近" + LABEL_SEP + "81.2");
  // The reported case, with the exact narrow space after each label.
  assert.equal(formatPillLabel(ready(0.985), ready(0.997)),
    "累计" + LABEL_SEP + "98.5 · 最近" + LABEL_SEP + "99.7");
  // Equal readings still print both, because they come from different bases.
  assert.equal(formatPillLabel(ready(0.5), ready(0.5)),
    "累计" + LABEL_SEP + "50 · 最近" + LABEL_SEP + "50");
  // Real zero is a measurement, not a missing value.
  assert.equal(formatPillLabel(ready(0), ready(1)),
    "累计" + LABEL_SEP + "0 · 最近" + LABEL_SEP + "100");
  // Only U+202F follows a label; the separator keeps ordinary spaces.
  for (const label of [
    formatPillLabel(ready(0.985), ready(0.997)),
    formatPillLabel(loading, ready(null)),
    formatPillLabel(off, ready(0.4)),
  ]) {
    assert.doesNotMatch(label, /t\/s|token/i);
    assert.doesNotMatch(label, /%/, label);
    assert.equal(label.split(LABEL_SEP).length, 3, label);
    assert.doesNotMatch(label, /\u00A0/, "no full no-break space");
  }
});

test("a whole reading drops only its .0 and keeps measured precision", () => {
  // 100 is the widest value; two of them still print in full.
  assert.equal(formatPillLabel(ready(1), ready(1)),
    "累计" + LABEL_SEP + "100 · 最近" + LABEL_SEP + "100");
  // Any whole percentage shortens the same way, not just 100.
  assert.equal(formatPillLabel(ready(0.98), ready(0.5)),
    "累计" + LABEL_SEP + "98 · 最近" + LABEL_SEP + "50");
  assert.equal(formatPillLabel(ready(0), ready(0)),
    "累计" + LABEL_SEP + "0 · 最近" + LABEL_SEP + "0");
  // A non-zero tenths digit keeps its one decimal.
  assert.equal(formatPillLabel(ready(0.999), ready(0.999)),
    "累计" + LABEL_SEP + "99.9 · 最近" + LABEL_SEP + "99.9");
  // The tooltip keeps the percent sign, one decimal and the full names.
  assert.equal(formatPillTitle(ready(1), ready(0.5)),
    "打开工作区用量 · 累计缓存 100.0% · 最近样本 50.0%");
});

test("each pill slot keeps its own placeholder and never borrows the other", () => {
  assert.equal(formatPillLabel(loading, ready(0.812)),
    "累计" + LABEL_SEP + "… · 最近" + LABEL_SEP + "81.2");
  assert.equal(formatPillLabel(off, ready(0.812)),
    "累计" + LABEL_SEP + "— · 最近" + LABEL_SEP + "81.2");
  assert.equal(formatPillLabel(ready(0.949), ready(null)),
    "累计" + LABEL_SEP + "94.9 · 最近" + LABEL_SEP + "—");
  assert.equal(formatPillLabel(off, loading),
    "累计" + LABEL_SEP + "— · 最近" + LABEL_SEP + "…");
  // A missing cumulative rate is never filled from the recent sample.
  assert.equal(formatPillLabel(ready(null), ready(0.812)),
    "累计" + LABEL_SEP + "— · 最近" + LABEL_SEP + "81.2");
  assert.equal(formatPillLabel({ kind: "unavailable", reason: "累计读取失败" }, ready(0.812)),
    "累计" + LABEL_SEP + "— · 最近" + LABEL_SEP + "81.2");
});

/**
 * Width estimate anchored to the parent's browser measurement of this plugin's
 * pill: `累计 98.5 · 最近 99.7` with ordinary spaces rendered 158 px at the
 * host's 12 px label size. Paseo v0.17.4 public styles give the non-text part as
 * 160 max width minus 12 + 12 padding, 8 gap and the 16 px icon = 48 px, so that
 * label is ~110 px against a 112 px text budget. Other strings are compared to
 * it with rough per-glyph deltas (CJK 12 px, digit 6.7 px, U+202F 2.4 px ≈
 * 0.2 em), so this is a style-bound estimate, never a real layout result.
 */
const PILL_TEXT_BUDGET = 160 - 12 - 12 - 8 - 16; // 112 px
const MEASURED_PLAIN_LABEL = 110; // px, parent browser measurement
function labelGlyphWidth(text) {
  const glyph = (char) => {
    if (char === "\u202F") return 2.4;
    if (char === " " || char === ".") return 3.4;
    if (char === "·") return 4.5;
    if (char === "…" || char === "—") return 12;
    if (char.charCodeAt(0) < 0x2e80) return 6.7; // digits, latin
    return 12; // CJK
  };
  return [...text].reduce((sum, char) => sum + glyph(char), 0);
}
const PLAIN_LABEL = "累计 98.5 · 最近 99.7";
function estimatedLabelWidth(label) {
  return MEASURED_PLAIN_LABEL + labelGlyphWidth(label) - labelGlyphWidth(PLAIN_LABEL);
}

test("the reported values and the widest pairs stay inside the 160 px style bound", () => {
  const reported = formatPillLabel(ready(0.985), ready(0.997));
  assert.equal(reported, "累计" + LABEL_SEP + "98.5 · 最近" + LABEL_SEP + "99.7");
  // The narrow space is what buys the room, so the plain-space form stays wider.
  assert.ok(estimatedLabelWidth(reported) < estimatedLabelWidth(PLAIN_LABEL));
  for (const label of [
    reported,
    formatPillLabel(ready(0.999), ready(0.999)),
    formatPillLabel(ready(1), ready(1)),
  ]) {
    assert.ok(estimatedLabelWidth(label) <= PILL_TEXT_BUDGET,
      `${label} ≈ ${estimatedLabelWidth(label).toFixed(1)} px > ${PILL_TEXT_BUDGET} px`);
  }
});

test("the pill title names both bases and explains a missing cumulative rate", () => {
  assert.equal(formatPillTitle(ready(0.949), ready(0.812)),
    "打开工作区用量 · 累计缓存 94.9% · 最近样本 81.2%");
  assert.equal(formatPillTitle(off, ready(0.812)),
    "打开工作区用量 · 累计缓存 —（累计统计已关闭） · 最近样本 81.2%");
  assert.equal(formatPillTitle({ kind: "unavailable", reason: "不在本机累计名单" }, ready(0.4)),
    "打开工作区用量 · 累计缓存 —（不在本机累计名单） · 最近样本 40.0%");
  assert.equal(formatPillTitle({ kind: "unavailable", reason: "累计读取失败：累计用量读取失败" }, ready(null)),
    "打开工作区用量 · 累计缓存 —（累计读取失败：累计用量读取失败） · 最近样本 —（尚无有效最近样本）");
  assert.equal(formatPillTitle(loading, ready(0.4)),
    "打开工作区用量 · 累计缓存 … · 最近样本 40.0%");
  // A finished cumulative read with no valid snapshot says so instead of showing a number.
  assert.equal(formatPillTitle(ready(null), ready(0.4)),
    "打开工作区用量 · 累计缓存 —（尚无有效累计快照） · 最近样本 40.0%");
  // Real zero prints as a value in both the line and the title.
  assert.equal(formatPillTitle(ready(0), ready(0)),
    "打开工作区用量 · 累计缓存 0.0% · 最近样本 0.0%");
});

test("the newest completed turn wins even when it has no speed", () => {
  const fast = turn(1_000, 900, 1_000);
  const newerMissing = turn(2_000, null, 1_500);
  assert.equal(latestCompletedTurn(fast, newerMissing), newerMissing);
  assert.equal(latestCompletedTurn(newerMissing, fast), newerMissing);
  assert.equal(latestCompletedTurn(null, null), null);
});

test("the panel keeps distinct recent and cumulative speeds while the pill carries only rates", () => {
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
  // …and neither leaks into the composer pill, which shows the two cache rates.
  assert.equal(formatPillLabel(ready(0.949), ready(0.812)),
    "累计" + LABEL_SEP + "94.9 · 最近" + LABEL_SEP + "81.2");
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
