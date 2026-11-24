import test from "node:test";
import assert from "node:assert/strict";
import { afterSessionFailure, planSessionNaming } from "../shared/session-naming.ts";
import { isSubstantiveAnswer, planSegments, buildTranscriptTurns } from "../shared/transcript.ts";

function plan(overrides = {}) {
  return planSessionNaming({
    state: undefined,
    currentTitle: "先看 Codex 为什么走 WebSocket",
    prompt: "先看 Codex 为什么走 WebSocket",
    hasAnswer: true,
    turnId: "t1",
    completed: true,
    maxAttempts: 2,
    provisional: true,
    ...overrides,
  });
}

test("the first completed turn with a real answer spends attempt 1", () => {
  assert.deepEqual(plan(), { kind: "generate", attempt: 1, repair: false });
});

test("a failed or tool-only turn never spends an attempt", () => {
  assert.deepEqual(plan({ hasAnswer: false }), { kind: "wait", reason: "awaiting_answer" });
  assert.deepEqual(plan({ completed: false }), { kind: "wait", reason: "awaiting_answer" });
});

test("a model failure keeps the provisional title and allows one later turn", () => {
  const afterFailure = { status: "pending", error: "model_failed", attempts: 1, lastTurnId: "t1", at: "2026-11-24T00:00:00Z" };
  // Same turn redelivered: duplicate event, restart or retry.
  assert.deepEqual(plan({ state: afterFailure, turnId: "t1" }), { kind: "wait", reason: "duplicate_turn" });
  // A reconcile scan has no turn id and must not retry.
  assert.deepEqual(plan({ state: afterFailure, turnId: null }), { kind: "wait", reason: "no_new_turn" });
  // A different completed turn gets the last attempt.
  assert.deepEqual(plan({ state: afterFailure, turnId: "t2" }), { kind: "generate", attempt: 2, repair: false });
});

test("a provider outage spends one attempt and still allows the later turn", () => {
  const failed = afterSessionFailure({
    errorCode: "provider_unavailable",
    attempt: 1,
    maxAttempts: 2,
    turnId: "t1",
    repair: false,
    at: "x",
  });
  assert.equal(failed.status, "pending");
  assert.equal(failed.error, "provider_unavailable");
  assert.equal(failed.title, undefined, "no fallback title is ever recorded as success");
  // The provider may recover; the next different completed turn gets the last try.
  assert.deepEqual(plan({ state: failed, turnId: "t2" }), { kind: "generate", attempt: 2, repair: false });
  assert.deepEqual(plan({ state: failed, turnId: "t1" }), { kind: "wait", reason: "duplicate_turn" });
  const spent = afterSessionFailure({
    errorCode: "provider_unavailable", attempt: 2, maxAttempts: 2, turnId: "t2", repair: false, at: "x",
  });
  assert.equal(spent.status, "skipped");
});

test("success and exhaustion both stop for good", () => {
  const done = { status: "done", title: "排查 Codex 连接方式", attempts: 1, lastTurnId: "t1", at: "x" };
  assert.deepEqual(plan({ state: done, currentTitle: "先看 Codex 为什么走 WebSocket", turnId: "t2" }), {
    kind: "blocked",
    reason: "manual_title",
  });
  const spent = { status: "skipped", error: "model_failed", attempts: 2, lastTurnId: "t2", at: "x" };
  assert.deepEqual(plan({ state: spent, turnId: "t3" }), { kind: "blocked", reason: "exhausted" });
});

test("existing explicit, legacy and manual titles are never overwritten", () => {
  assert.deepEqual(plan({ provisional: false, currentTitle: "我自己的标题" }), { kind: "blocked", reason: "manual_title" });
  assert.deepEqual(plan({ state: { status: "legacy", at: "x" } }), { kind: "blocked", reason: "legacy" });
  assert.deepEqual(plan({ state: { status: "generating", at: "x" } }), { kind: "blocked", reason: "in_flight" });
});

test("a legacy done+model_failed entry gets one repair only while its title is untouched", () => {
  const legacy = { status: "done", title: "先看 Codex 为什么走", error: "model_failed", at: "x" };
  assert.deepEqual(
    plan({ state: legacy, currentTitle: "先看 Codex 为什么走", provisional: false }),
    { kind: "generate", attempt: 2, repair: true },
  );
  // A manual rename since then means the recorded title is no longer live.
  assert.deepEqual(
    plan({ state: legacy, currentTitle: "用户改过的标题", provisional: false }),
    { kind: "blocked", reason: "manual_title" },
  );
  // A legacy entry written by an outage is repairable the same way, once.
  const legacyOutage = { status: "done", title: "修复登录问题", error: "provider_unavailable", at: "x" };
  assert.deepEqual(
    plan({ state: legacyOutage, currentTitle: "修复登录问题", provisional: false }),
    { kind: "generate", attempt: 2, repair: true },
  );
  // A done entry with no failure code may be a real model title: never repair it.
  assert.deepEqual(
    plan({ state: { status: "done", title: "真实模型标题", at: "x" }, currentTitle: "真实模型标题", provisional: false }),
    { kind: "blocked", reason: "manual_title" },
  );

  // The repair is spent once.
  assert.deepEqual(
    plan({ state: { ...legacy, repairUsed: true }, currentTitle: "先看 Codex 为什么走", provisional: false }),
    { kind: "blocked", reason: "manual_title" },
  );
  // The repair still needs a real answer.
  assert.deepEqual(
    plan({ state: legacy, currentTitle: "先看 Codex 为什么走", provisional: false, hasAnswer: false }),
    { kind: "wait", reason: "awaiting_answer" },
  );
  // A failed or canceled turn can carry partially streamed assistant text. That
  // must not spend the single repair: the turn has to be a completed one.
  assert.deepEqual(
    plan({ state: legacy, currentTitle: "先看 Codex 为什么走", provisional: false, completed: false }),
    { kind: "wait", reason: "awaiting_answer" },
  );
  // Once that completed repair is spent, nothing runs again.
  assert.deepEqual(
    plan({
      state: { ...legacy, repairUsed: true, attempts: 2 },
      currentTitle: "先看 Codex 为什么走",
      provisional: false,
    }),
    { kind: "blocked", reason: "manual_title" },
  );
});

test("a substantive answer is required, not a tool-only or empty reply", () => {
  assert.equal(isSubstantiveAnswer("查完了：Codex 客户端先尝试 WebSocket。"), true);
  assert.equal(isSubstantiveAnswer("   "), false);
  assert.equal(isSubstantiveAnswer(null), false);
  assert.equal(isSubstantiveAnswer("<environment_context>x</environment_context>"), false);
  assert.equal(isSubstantiveAnswer("ok"), false);
});

test("segments stay contiguous and in order, and a capped plan reports partial coverage", () => {
  const turns = Array.from({ length: 6 }, (_, index) => ({
    id: `t${index}`,
    text: `用户：第 ${index} 轮 ${"内容".repeat(400)}`,
    chars: 806,
  }));
  const capped = planSegments(turns, { segmentChars: 800, maxSegments: 3 });
  assert.equal(capped.coversAll, false);
  assert.equal(capped.segments.length, 3);
  assert.deepEqual(capped.segments.map((segment) => segment[0].id), ["t0", "t1", "t2"]);

  const paired = planSegments(turns, { segmentChars: 1_700, maxSegments: 3 });
  assert.equal(paired.coversAll, true);
  assert.deepEqual(paired.segments.map((segment) => segment.map((turn) => turn.id)), [
    ["t0", "t1"],
    ["t2", "t3"],
    ["t4", "t5"],
  ]);
});

test("turns are grouped chronologically and keep a question before its answer", () => {
  const turns = buildTranscriptTurns([
    { type: "user_message", text: "先看 Codex 为什么走 WebSocket", turnId: "t1" },
    { type: "assistant_message", text: "因为 daemon 与宿主之间是长连接", turnId: "t1" },
    { type: "user_message", text: "那 CCHP 上游呢", turnId: "t2" },
  ]);
  assert.deepEqual(turns.map((turn) => turn.id), ["t1", "t2"]);
  assert.ok(turns[0].text.startsWith("用户：先看 Codex"));
  assert.ok(turns[0].text.includes("助手：因为 daemon"));
});
