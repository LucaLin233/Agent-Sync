import test from "node:test";
import assert from "node:assert/strict";
import {
  cleanModelTitle,
  ensureHan,
  fallbackProjectTitle,
  fallbackTaskTitle,
  hasHan,
  isAcceptableTitle,
  isProvisional,
  provisionalTitle,
  sanitizeConversationTitle,
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

test("fallback keeps only technical Latin names and always ends with Han", () => {
  assert.equal(fallbackTaskTitle({ prompt: "Fix login bug", baseName: "Paseo", maxChars: 28 }), "修复登录问题");
  assert.equal(fallbackTaskTitle({ prompt: "更新用户资料", baseName: "app", maxChars: 28 }), "更新用户资料");
  assert.equal(fallbackTaskTitle({ prompt: "", baseName: "Paseo", maxChars: 28 }), "处理 Paseo");
  assert.equal(fallbackTaskTitle({ prompt: "", baseName: "app", maxChars: 28 }), "处理工作区");
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
  assert.equal(fallbackProjectTitle("my-project", 20), "项目 my-project");
  assert.equal(fallbackProjectTitle("Program Files", 20), "新项目");
  assert.equal(fallbackProjectTitle("工作区指标", 20), "工作区指标");
  assert.ok(hasHan(fallbackProjectTitle("", 20)));
});

test("one generated title is reused for a workspace/session pair", () => {
  assert.equal(titleForPair("修复登录问题", "处理工作区", 28), "修复登录问题");
  assert.equal(titleForPair("Fix login", "修复登录问题", 28), "修复登录问题");
});

test("fallback turns mixed Chinese/English lines into natural Chinese", () => {
  assert.equal(fallbackTaskTitle({ prompt: "修复 the login redirect loop", maxChars: 28 }), "修复登录跳转循环");
  assert.equal(fallbackTaskTitle({ prompt: "修复登录问题 the bug", maxChars: 28 }), "修复登录问题");
  assert.equal(fallbackTaskTitle({ prompt: "优化 Codex 会话", maxChars: 28 }), "优化 Codex 会话");
  assert.equal(fallbackTaskTitle({ prompt: "Fix the aaaaaaaaaaaaaaaa 中文", maxChars: 28 }), "处理任务");
});

test("fallback follows Chinese action plus meaningful proper nouns", () => {
  assert.equal(fallbackTaskTitle({ prompt: "Optimize Codex session handling", maxChars: 28 }), "优化 Codex 会话");
  assert.equal(fallbackTaskTitle({ prompt: "Update Paseo plugin", maxChars: 28 }), "更新 Paseo 插件");
  assert.equal(fallbackTaskTitle({ prompt: "Add OAuth callback", maxChars: 28 }), "新增 OAuth 回调");
  assert.equal(
    fallbackTaskTitle({ prompt: "Extend workspace usage plugin with token speed and first-token latency", maxChars: 28 }),
    "扩展工作区用量插件",
  );
});

test("ordinary English is rejected with punctuation, caps or hyphens", () => {
  assert.equal(sanitizeModelTitle("修复 login bug", 28), null);
  assert.equal(sanitizeModelTitle("修复 LOGIN BUG.", 28), null);
  assert.equal(sanitizeModelTitle("修复 login-bug", 28), null);
  assert.equal(sanitizeModelTitle("好", 28), null);
  assert.equal(sanitizeModelTitle("优化 Codex 会话", 28), "优化 Codex 会话");
  assert.equal(sanitizeModelTitle("更新 server/engine.ts", 28), "更新 server/engine.ts");
  assert.equal(sanitizeModelTitle("修复 v0.17.3 回归", 28), "修复 v0.17.3 回归");
});

test("manual titles are gated by Chinese content, not a Latin word list", () => {
  // Real answers that were rejected only because the product word was absent
  // from the automatic vocabulary. Manual summaries keep them as written.
  assert.equal(sanitizeConversationTitle("对比 Exa 与 Keenable 的检索结果", 28), "对比 Exa 与 Keenable 的检索结果");
  assert.equal(sanitizeConversationTitle("排查 TS 类型错误", 28), "排查 TS 类型错误");
  assert.equal(sanitizeConversationTitle("整理 agent-sync 提示词与技能", 28), "整理 agent-sync 提示词与技能");
  assert.equal(sanitizeConversationTitle("整理 agent-sync 提示词与技能", 20), "整理 agent-sync 提示词与技能");

  // An unfamiliar but real proper noun is not rejected just because nobody
  // added a table entry for it.
  assert.equal(sanitizeConversationTitle("整理 NimbusDesk 报表", 28), "整理 NimbusDesk 报表");
  assert.equal(sanitizeConversationTitle("修复 login bug", 28), "修复 login bug");

  // Genuinely unusable answers still fail: no Han, one Han, empty or control.
  assert.equal(sanitizeConversationTitle("Fix login bug", 28), null);
  assert.equal(sanitizeConversationTitle("Exa Keenable TS", 28), null);
  assert.equal(sanitizeConversationTitle("好", 28), null);
  assert.equal(sanitizeConversationTitle("", 28), null);
  assert.equal(sanitizeConversationTitle("修复\u0000登录", 28), null);

  // Automatic naming keeps its stricter word-by-word gate.
  assert.equal(sanitizeModelTitle("修复 login bug", 28), null);
  assert.equal(sanitizeModelTitle("整理 agent-sync 提示词与技能", 28), null);
  assert.equal(isAcceptableTitle("整理 agent-sync 提示词与技能"), false);
  assert.equal(isAcceptableTitle("优化 Codex 会话"), true);
});

test("manual truncation never cuts a Latin term and still requires Chinese", () => {
  assert.equal(sanitizeConversationTitle("排查标题中文化插件", 28), "排查标题中文化插件");
  assert.equal(
    sanitizeConversationTitle("重构工作区标题的会话摘要生成 pathwayhandling", 12),
    "重构工作区标题的会话摘要",
  );
  const term = sanitizeConversationTitle("排查 paseo-chinese-titles 插件的手动重生成", 20);
  assert.ok(term === null || !/[A-Za-z]$/u.test(term), String(term));
  assert.equal(sanitizeConversationTitle("Fix login bug 与 Exa", 4), null);
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

test("plugin data paths cannot escape the plugin directory", async () => {
  const { assertPluginPath, pluginDataDir, safePluginPath } = await import("../server/state.ts");
  const root = pluginDataDir();
  assert.equal(assertPluginPath(root), root);
  assert.equal(safePluginPath("helper", "bootstrap"), `${root}/helper/bootstrap`);
  assert.throws(() => safePluginPath("../escape"));
  assert.throws(() => safePluginPath("/absolute"));
  assert.throws(() => assertPluginPath(`${root}/../escape`));
});

test("plugin storage is scoped by hashed PASEO_HOME, not by the env path", async () => {
  const { createHash } = await import("node:crypto");
  const { pluginDataDir } = await import("../server/state.ts");
  const previous = process.env.PASEO_HOME;
  try {
    process.env.PASEO_HOME = "/synthetic/daemon-a";
    const a = pluginDataDir();
    assert.ok(a.endsWith(createHash("sha256").update("/synthetic/daemon-a").digest("hex").slice(0, 32)));
    assert.ok(!a.includes("/synthetic/daemon-a"));
    process.env.PASEO_HOME = "/synthetic/daemon-b";
    assert.notEqual(pluginDataDir(), a);
  } finally {
    if (previous === undefined) delete process.env.PASEO_HOME;
    else process.env.PASEO_HOME = previous;
  }
});

test("Codex catalog lists only ready Codex aliases with linked models and thinking options", async () => {
  const { listTitleProviderOptions } = await import("../server/provider.ts");
  const paseo = {
    config: { get: async () => ({ config: { providers: { cchp: { extends: "codex", label: "CCHP" }, pi: {} } } }) },
    providers: {
      snapshot: async () => ({ entries: [
        { provider: "cchp", status: "ready", enabled: true, label: "CCHP host", models: [
          { id: "deepseek-flash", label: "DeepSeek Flash", isDefault: true, defaultThinkingOptionId: "low", thinkingOptions: [{ id: "low", label: "Low" }, { id: "high", label: "High" }] },
        ] },
        { provider: "pi", status: "ready", enabled: true, models: [{ id: "pi-model", label: "Pi" }] },
      ] }),
      listModels: async () => ({ models: [] }),
    },
  };
  const catalog = await listTitleProviderOptions(paseo);
  assert.deepEqual(catalog.providers.map((provider) => provider.id), ["cchp"]);
  assert.equal(catalog.providers[0].label, "CCHP host");
  assert.equal(catalog.providers[0].models[0].id, "deepseek-flash");
  assert.deepEqual(catalog.providers[0].models[0].thinkingOptions.map((option) => option.id), ["low", "high"]);
  assert.equal(catalog.providers[0].models[0].isDefault, true);
});
