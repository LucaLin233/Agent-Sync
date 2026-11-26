import assert from "node:assert/strict";
import { test } from "node:test";
import { latestCacheSample, metricFirstTokenMs, observeTurn, parseMetricDuration, sessionKindOf, summarizeLatestSamples } from "../shared/metrics.ts";

test("recent samples sum token counts, including cache reads in total input", () => {
  const smaller = latestCacheSample("codex", { inputTokens: 100, cachedInputTokens: 80 });
  const larger = latestCacheSample("codex", { inputTokens: 900, cachedInputTokens: 0 });
  assert.deepEqual(summarizeLatestSamples([smaller, null, larger]), {
    covered: 2,
    input: 1_000,
    cached: 80,
    rate: 0.08,
  });
  assert.equal(summarizeLatestSamples([larger]).rate, 0);
});

test("unknown scope, missing counts, and invalid denominators have no rate", () => {
  const samples = [
    latestCacheSample("codex", null),
    latestCacheSample("codex", { inputTokens: 100 }),
    latestCacheSample("codex", { cachedInputTokens: 1 }),
    latestCacheSample("codex", { inputTokens: 0, cachedInputTokens: 0 }),
    latestCacheSample("codex", { inputTokens: 50, cachedInputTokens: 51 }),
    latestCacheSample("codex", { inputTokens: 50, cachedInputTokens: -1 }),
    latestCacheSample("codex", { inputTokens: Infinity, cachedInputTokens: 1 }),
    latestCacheSample("pi", { inputTokens: 100, cachedInputTokens: 50 }),
    latestCacheSample("claude", { inputTokens: 100, cachedInputTokens: 50 }),
  ];
  assert.deepEqual(samples, Array(samples.length).fill(null));
  assert.deepEqual(summarizeLatestSamples(samples), { covered: 0, input: 0, cached: 0, rate: null });
});

test("provider aliases use the Codex cache basis only with a Codex adapter marker", () => {
  const usage = { inputTokens: 100, cachedInputTokens: 40 };
  const cchp = latestCacheSample("cchp", usage, "codex");
  const gdr = latestCacheSample("gdr", usage, "codex");
  const unknown = latestCacheSample("unknown", usage);
  assert.deepEqual(summarizeLatestSamples([cchp, gdr, unknown]), {
    covered: 2,
    input: 200,
    cached: 80,
    rate: 0.4,
  });
  assert.equal(latestCacheSample("cchp", usage), null);
  assert.equal(latestCacheSample("unknown", usage, "claude"), null);
  assert.equal(latestCacheSample("unknown", usage, { provider: "codex" }), null);
});

const empty = { active: null, last: null };
const start = { kind: "start", turnId: "a", timestamp: 1_000 };
const assistant = { kind: "assistant", turnId: "a", timestamp: 1_120, visible: true };
const complete = { kind: "completed", turnId: "a", timestamp: 3_000, outputTokens: 240 };

test("timing uses the first visible assistant text and matching whole turn only", () => {
  const result = [
    start,
    { ...assistant, turnId: "other", timestamp: 1_050 },
    assistant,
    { ...assistant, timestamp: 1_300 },
    { ...complete, turnId: "other" },
    complete,
    complete,
  ].reduce(observeTurn, empty);
  assert.deepEqual(result.last, {
    turnId: "a",
    firstVisibleMs: 120,
    elapsedMs: 2_000,
    outcome: "completed",
    outputPerSecond: 120,
    providerFirstTokenMs: null,
  });
});

test("observation gaps and missing output do not become measurements", () => {
  assert.deepEqual([assistant, complete].reduce(observeTurn, empty), empty);
  assert.deepEqual([start, assistant, { kind: "gap" }, complete].reduce(observeTurn, empty), empty);
  assert.deepEqual([start, assistant, complete, { kind: "replacement" }].reduce(observeTurn, empty), empty);
  assert.deepEqual([start, { ...complete, outputTokens: null }].reduce(observeTurn, empty).last, {
    turnId: "a",
    firstVisibleMs: null,
    elapsedMs: 2_000,
    outcome: "completed",
    outputPerSecond: null,
    providerFirstTokenMs: null,
  });
});

test("blank, whitespace-only, and non-assistant items are not the first visible text", () => {
  const blanks = [
    { kind: "assistant", turnId: "a", timestamp: 1_050, visible: false },
    { kind: "assistant", turnId: "a", timestamp: 1_060, visible: false },
    assistant,
  ];
  const result = [start, ...blanks].reduce(observeTurn, empty);
  assert.equal(result.active.firstAssistantAt, 1_120);
  assert.equal(result.last, null);
});

test("a completed turn keeps its rollout-independent timing only", () => {
  const result = [start, assistant, complete].reduce(observeTurn, empty);
  assert.equal("startedAt" in result.last, false);
  assert.equal("endedAt" in result.last, false);
});

test("the SDK TTFT metric is read back from Paseo's formatted duration", () => {
  assert.equal(parseMetricDuration("<0.1s"), 0);
  assert.equal(parseMetricDuration("1.2s"), 1_200);
  assert.equal(parseMetricDuration("1m 5s"), 65_000);
  assert.equal(parseMetricDuration("fast"), null);
  assert.equal(metricFirstTokenMs([{ label: "Elapsed", value: "9.0s" }, { label: "TTFT", value: "0.8s" }]), 800);
  assert.equal(metricFirstTokenMs(undefined), null);
});

test("a completed Claude turn carries the provider first token into the measurement", () => {
  const empty = { active: null, last: null };
  const result = [
    { kind: "start", turnId: "a", timestamp: 1_000 },
    { kind: "completed", turnId: "a", timestamp: 3_000, outputTokens: 100, providerFirstTokenMs: 700 },
  ].reduce(observeTurn, empty);
  assert.equal(result.last.providerFirstTokenMs, 700);
  assert.equal(result.last.outputPerSecond, 50);
});

test("custom providers are classified by the adapter marker", () => {
  assert.equal(sessionKindOf("claude-cchp", "claude"), "claude");
  assert.equal(sessionKindOf("cchp", "codex"), "codex");
  assert.equal(sessionKindOf("claude"), "claude");
  assert.equal(sessionKindOf("opencode", "opencode"), null);
});
