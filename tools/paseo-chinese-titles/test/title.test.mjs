import test from "node:test";
import assert from "node:assert/strict";
import {
  cleanModelTitle,
  ensureHan,
  fallbackProjectTitle,
  fallbackTaskTitle,
  hasHan,
  isProvisional,
  provisionalTitle,
  sanitizeModelTitle,
  titleForPair,
  truncateChars,
} from "../shared/title.ts";
import { settingsSchema } from "../shared/settings.ts";

test("model titles are cleaned and validated as Chinese", () => {
  assert.equal(sanitizeModelTitle("  修复登录问题  ", 20), "修复登录问题");
  assert.equal(sanitizeModelTitle('"新增 OAuth 回调"', 20), "新增 OAuth 回调");
  assert.equal(sanitizeModelTitle("```\n更新 Paseo 插件\n```", 20), "更新 Paseo 插件");
  assert.equal(sanitizeModelTitle('{"title":"重构 工作区 标题"}', 20), "重构 工作区 标题");
  assert.equal(sanitizeModelTitle("Fix login bug", 20), null);
  assert.equal(sanitizeModelTitle("", 20), null);
  assert.equal(sanitizeModelTitle("   ", 20), null);
  assert.equal(sanitizeModelTitle("React Router", 20), null);
});

test("model title is truncated without splitting surrogate pairs", () => {
  const value = `修复 ${"😀".repeat(20)} 问题`;
  const result = sanitizeModelTitle(value, 8);
  assert.equal(Array.from(result).length, 8);
  assert.ok(hasHan(result));
});

test("Paseo provisional titles are recognised conservatively", () => {
  const prompt = "Fix the login redirect loop\nsecond line";
  assert.equal(provisionalTitle(prompt), "Fix the login redirect loop");
  assert.equal(isProvisional("Fix the login redirect loop", prompt), true);
  assert.equal(isProvisional(null, prompt), true);
  assert.equal(isProvisional("手动标题", prompt), false);
});

test("fallback keeps ASCII product names but always ends with Han", () => {
  assert.equal(fallbackTaskTitle({ prompt: "Fix login bug", baseName: "Paseo", maxChars: 28 }), "修复 login bug");
  assert.equal(fallbackTaskTitle({ prompt: "更新用户资料", baseName: "app", maxChars: 28 }), "更新用户资料");
  assert.equal(fallbackTaskTitle({ prompt: "", baseName: "Paseo", maxChars: 28 }), "处理 Paseo");
  const truncated = fallbackTaskTitle({
    prompt: "Fix aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa中文",
    baseName: "app",
    maxChars: 10,
  });
  assert.ok(hasHan(truncated), truncated);
  assert.ok(Array.from(truncated).length <= 10);
});

test("ensureHan never returns Han-free text even at small limits", () => {
  for (const max of [1, 2, 3, 4, 10]) {
    const value = ensureHan("fix everything", max);
    assert.ok(hasHan(value), `${max}: ${value}`);
    assert.ok(Array.from(value).length <= max);
  }
  assert.equal(truncateChars("abcdef", 3), "abc");
});

test("project fallback is Chinese for ASCII display names", () => {
  assert.equal(fallbackProjectTitle("Paseo", 20), "项目 Paseo");
  assert.equal(fallbackProjectTitle("工作区指标", 20), "工作区指标");
  assert.ok(hasHan(fallbackProjectTitle("", 20)));
});

test("one generated title is reused for a workspace/session pair", () => {
  assert.equal(titleForPair("修复登录 bug", "处理 app", 28), "修复登录 bug");
  assert.equal(titleForPair("Fix login", "处理 app", 28), "处理 app");
});

test("session naming defaults off and provider stays empty for auto detection", () => {
  const parsed = settingsSchema.parse({});
  assert.equal(parsed.autoNameProjects, true);
  assert.equal(parsed.autoNameWorkspaces, true);
  assert.equal(parsed.autoNameSessions, false);
  assert.equal(parsed.provider, "");
  assert.equal(parsed.model, "");
  assert.equal(cleanModelTitle("标题：修复登录"), "修复登录");
});

test("the earliest real first task wins, with a deterministic tie break", async () => {
  const { pickFirstTask } = await import("../shared/first-task.ts");
  const later = { id: "B", text: "later", turnId: "t2", at: "2026-11-23T00:00:02Z" };
  const earlier = { id: "A", text: "earlier", turnId: "t1", at: "2026-11-23T00:00:01Z" };
  assert.equal(pickFirstTask([later, earlier]).id, "A");
  const tie1 = { id: "b", text: "x", turnId: "t", at: "2026-11-23T00:00:01Z" };
  const tie2 = { id: "a", text: "y", turnId: "t", at: "2026-11-23T00:00:01Z" };
  assert.equal(pickFirstTask([tie1, tie2]).id, "a");
  assert.equal(pickFirstTask([]), null);
});

test("generation plan counts session-only once, shared once, competitor twice", async () => {
  const { planTitleGeneration } = await import("../shared/generation-plan.ts");
  const sessionOnly = planTitleGeneration({ workspaceEligible: false, agentEligible: true, winnerIsAgent: false });
  assert.deepEqual(sessionOnly, { workspace: false, agent: "generate" });
  const sharedWinner = planTitleGeneration({ workspaceEligible: true, agentEligible: true, winnerIsAgent: true });
  assert.deepEqual(sharedWinner, { workspace: true, agent: "reuse-workspace" });
  const competitor = planTitleGeneration({ workspaceEligible: true, agentEligible: true, winnerIsAgent: false });
  assert.deepEqual(competitor, { workspace: true, agent: "generate" });
  const workspaceOnly = planTitleGeneration({ workspaceEligible: true, agentEligible: false, winnerIsAgent: false });
  assert.deepEqual(workspaceOnly, { workspace: true, agent: "none" });
  const none = planTitleGeneration({ workspaceEligible: false, agentEligible: false, winnerIsAgent: false });
  assert.deepEqual(none, { workspace: false, agent: "none" });
});
