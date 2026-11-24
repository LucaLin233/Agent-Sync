import test from "node:test";
import assert from "node:assert/strict";
import {
  buildConversationExcerpt,
  redactSecrets,
  withoutInjectedBlocks,
} from "../shared/transcript.ts";
import { readSessionConversation } from "../server/conversation.ts";
import {
  isSelectableSession,
  resolveSessionSelection,
  selectableSessionsFor,
} from "../shared/session-options.ts";
import { sanitizeConversationTitle } from "../shared/title.ts";
import { settingsSchema } from "../shared/settings.ts";

test("hidden events, tool rows and injected harness blocks never reach the excerpt", () => {
  const excerpt = buildConversationExcerpt([
    { type: "user_message", text: "帮我排查标题中文化插件", turnId: "t1" },
    { type: "reasoning", text: "INTERNAL-REASONING" },
    { type: "tool_call", text: "TOOL-OUTPUT" },
    { type: "notification", text: "SYSTEM-NOTIFICATION" },
    { type: "todo", text: "TODO-LIST" },
    { type: "compaction", text: "COMPACTION" },
    { type: "plugin", text: "PLUGIN-ROW" },
    { type: "assistant_message", text: "先看插件入口", turnId: "t1" },
    {
      type: "user_message",
      text: "<environment_context>cwd=/root/secret</environment_context>\n继续看手动按钮",
      turnId: "t2",
    },
  ]);
  assert.equal(excerpt.text.includes("INTERNAL-REASONING"), false);
  assert.equal(excerpt.text.includes("TOOL-OUTPUT"), false);
  assert.equal(excerpt.text.includes("SYSTEM-NOTIFICATION"), false);
  assert.equal(excerpt.text.includes("TODO-LIST"), false);
  assert.equal(excerpt.text.includes("COMPACTION"), false);
  assert.equal(excerpt.text.includes("PLUGIN-ROW"), false);
  assert.equal(excerpt.text.includes("environment_context"), false);
  assert.ok(excerpt.text.includes("帮我排查标题中文化插件"));
  assert.ok(excerpt.text.includes("继续看手动按钮"));
});

test("obvious credentials are redacted before the excerpt leaves the daemon", () => {
  const text = [
    "导出时用了 GH_TOKEN=synthetic_token_value 和 CCHP_TOKEN=synthetic-cchp-value。",
    '配置 {"password":"hunter2-synthetic","apiKey":"sk-synthetic-abcdefghijklmnop"}',
    "Authorization: Bearer synthetic-bearer-value",
    "ghp_syntheticsyntheticsynthetic",
  ].join("\n");
  const cleaned = redactSecrets(text);
  for (const secret of [
    "synthetic_token_value",
    "synthetic-cchp-value",
    "hunter2-synthetic",
    "sk-synthetic-abcdefghijklmnop",
    "synthetic-bearer-value",
    "ghp_syntheticsyntheticsynthetic",
  ]) {
    assert.equal(cleaned.includes(secret), false, `leaked ${secret}: ${cleaned}`);
  }
  assert.ok(cleaned.includes("已移除凭据"));
  const excerpt = buildConversationExcerpt([{ type: "user_message", text, turnId: "t1" }]);
  assert.equal(excerpt.text.includes("synthetic_token_value"), false);
});

test("a long conversation keeps its first task and newest turns, not the old middle", () => {
  const entries = [];
  for (let index = 0; index < 40; index += 1) {
    entries.push({ type: "user_message", text: `第 ${index} 轮：中间话题 ${"细节".repeat(60)}`, turnId: `t${index}` });
    entries.push({ type: "assistant_message", text: `第 ${index} 轮答复 ${"说明".repeat(60)}`, turnId: `t${index}` });
  }
  const excerpt = buildConversationExcerpt(entries, { maxChars: 900, maxTurns: 4 });
  assert.ok(excerpt.text.includes("第 0 轮"), excerpt.text.slice(0, 120));
  assert.ok(excerpt.text.includes("第 39 轮"), "newest turn must survive");
  assert.ok(excerpt.text.includes("第 20 轮") === false, "old middle turns are dropped first");
  assert.ok(Array.from(excerpt.text).length <= 900);
});

test("a last-turn tail cut never truncates the newest text from the front", () => {
  const entries = [
    { type: "user_message", text: `首任务 ${"甲".repeat(500)}`, turnId: "t0" },
    { type: "user_message", text: `最新话题结尾标记 ${"乙".repeat(500)} 收尾`, turnId: "t1" },
  ];
  const excerpt = buildConversationExcerpt(entries, { maxChars: 400, maxMessageChars: 400 });
  assert.ok(Array.from(excerpt.text).length <= 400);
  assert.ok(excerpt.text.includes("首任务"), "the first task survives");
  assert.ok(excerpt.text.includes("最新话题结尾标记"), "the newest turn is represented, not dropped");
});

test("an empty conversation yields no excerpt and no title", () => {
  assert.deepEqual(buildConversationExcerpt([]), { text: "", turns: 0 });
  assert.deepEqual(
    buildConversationExcerpt([{ type: "reasoning", text: "only thinking" }]),
    { text: "", turns: 0 },
  );
});

test("conversation titles are validated and truncated at safe boundaries", () => {
  assert.equal(sanitizeConversationTitle("排查标题中文化插件", 28), "排查标题中文化插件");
  assert.equal(sanitizeConversationTitle("对比 Exa 与 Keenable 的检索结果", 28), "对比 Exa 与 Keenable 的检索结果");
  assert.equal(sanitizeConversationTitle("Fix login bug", 28), null);
  assert.equal(sanitizeConversationTitle("", 28), null);
  assert.equal(sanitizeConversationTitle("重构工作区标题的会话摘要生成 pathwayhandling", 12), "重构工作区标题的会话摘要");
  const term = sanitizeConversationTitle("排查 paseo-chinese-titles 插件的手动重生成", 20);
  assert.ok(term === null || !/[A-Za-z]$/u.test(term), String(term));
});

test("only ordinary user sessions are selectable", () => {
  const eligible = { id: "a", workspaceId: "w1", labels: {}, background: false };
  assert.equal(isSelectableSession(eligible), true);
  assert.equal(isSelectableSession({ ...eligible, background: true }), false);
  assert.equal(isSelectableSession({ ...eligible, internal: true }), false);
  assert.equal(isSelectableSession({ ...eligible, parentAgentId: "parent" }), false);
  assert.equal(isSelectableSession({ ...eligible, labels: { "paseo.parent-agent-id": "parent" } }), false);
  assert.equal(isSelectableSession({ ...eligible, labels: { "paseo-chinese-titles.helper": "1" } }), false);
  assert.equal(isSelectableSession({ ...eligible, labels: { "better-paseo.purpose": "title-generation" } }), false);
  assert.equal(isSelectableSession({ ...eligible, archivedAt: "2026-11-23T00:00:00Z" }), false);
});

test("session selection: one is preselected, several need a real choice", () => {
  const one = selectableSessionsFor([
    { id: "a", workspaceId: "w1", lastActivityAt: "2026-11-23T00:00:00Z" },
    { id: "b", workspaceId: "w2", lastActivityAt: "2026-11-24T00:00:00Z" },
  ], "w1");
  assert.deepEqual(one.map((session) => session.id), ["a"]);
  assert.equal(resolveSessionSelection(one, null), "a");

  const two = selectableSessionsFor([
    { id: "old", workspaceId: "w1", lastActivityAt: "2026-11-20T00:00:00Z" },
    { id: "new", workspaceId: "w1", lastActivityAt: "2026-11-24T00:00:00Z" },
  ], "w1");
  assert.deepEqual(two.map((session) => session.id), ["new", "old"]);
  assert.equal(resolveSessionSelection(two, null), null, "never silently pick the most recent");
  assert.equal(resolveSessionSelection(two, "old"), "old");
  assert.equal(resolveSessionSelection(two, "gone"), null);
});

function fakeTimeline(entries) {
  const seqOf = (index) => ({ epoch: "e1", seq: index + 1 });
  const page = (start, end) => entries.slice(start, end).map((item, offset) => ({
    provider: "codex",
    item,
    turnId: item.turnId,
    timestamp: item.timestamp ?? "2026-11-23T00:00:00.000Z",
    seqStart: start + offset + 1,
    seqEnd: start + offset + 1,
    sourceSeqRanges: [],
    collapsed: [],
  }));
  return {
    refetch: async (options = {}) => {
      const limit = options.limit ?? 20;
      if (options.direction === "tail") {
        const start = Math.max(0, entries.length - limit);
        return {
          direction: "tail",
          projection: "projected",
          hasOlder: start > 0,
          hasNewer: false,
          startCursor: seqOf(start),
          endCursor: seqOf(entries.length - 1),
          entries: page(start, entries.length),
          error: null,
        };
      }
      if (options.direction === "before") {
        const end = (options.cursor?.seq ?? 1) - 1;
        const start = Math.max(0, end - limit);
        return {
          direction: "before",
          projection: "projected",
          hasOlder: start > 0,
          hasNewer: true,
          startCursor: seqOf(start),
          endCursor: seqOf(end - 1),
          entries: page(start, end),
          error: null,
        };
      }
      const start = options.cursor?.seq ? options.cursor.seq : 0;
      const end = Math.min(entries.length, start + limit);
      return {
        direction: "after",
        projection: "projected",
        hasOlder: start > 0,
        hasNewer: end < entries.length,
        startCursor: seqOf(start),
        endCursor: seqOf(end - 1),
        entries: page(start, end),
        error: null,
      };
    },
  };
}

test("a long session reads its real first task plus the newest turns", async () => {
  const entries = [{ type: "user_message", text: "原始任务：排查标题中文化插件", turnId: "t0", timestamp: "2026-11-20T00:00:00Z" }];
  for (let index = 1; index <= 150; index += 1) {
    entries.push({ type: "assistant_message", text: `较早答复 ${index}`, turnId: `t${index}`, timestamp: "2026-11-21T00:00:00Z" });
    entries.push({ type: "reasoning", text: `隐藏推理 ${index}`, turnId: `t${index}`, timestamp: "2026-11-21T00:00:00Z" });
  }
  entries.push({ type: "user_message", text: "现在改成概括会话最近讨论什么", turnId: "t200", timestamp: "2026-11-23T00:00:00Z" });
  entries.push({ type: "assistant_message", text: "好的，正在补手动选择会话", turnId: "t200", timestamp: "2026-11-23T00:00:01Z" });

  const timeline = fakeTimeline(entries);
  const paseo = { agents: { ref: () => ({ timeline }) } };
  const excerpt = await readSessionConversation(paseo, "a1");
  assert.ok(excerpt);
  assert.ok(excerpt.text.includes("原始任务：排查标题中文化插件"), "first task must be present");
  assert.ok(excerpt.text.includes("现在改成概括会话最近讨论什么"), "newest turn must be present");
  assert.equal(excerpt.text.includes("隐藏推理"), false);
});

test("a read error yields no conversation, so nothing can be generated", async () => {
  const paseo = {
    agents: {
      ref: () => ({
        timeline: { refetch: async () => ({ error: "boom", entries: [] }) },
      }),
    },
  };
  assert.equal(await readSessionConversation(paseo, "a1"), null);
});

test("the AGENTS.md wrapper header is stripped along with its block", () => {
  const text = withoutInjectedBlocks(
    "# AGENTS.md instructions for /root/agent/worktree\n\n<INSTRUCTIONS>\nrole text\n</INSTRUCTIONS>\n\n把面板改成选择会话\n",
  );
  assert.equal(text.includes("AGENTS.md"), false);
  assert.equal(text.includes("role text"), false);
  assert.ok(text.includes("把面板改成选择会话"));
});

test("injected blocks are stripped but the user's own prose survives", () => {
  const text = withoutInjectedBlocks(
    "<permissions instructions>sandbox_mode</permissions instructions>\n请把标题改成中文\n```\n" + "x".repeat(400) + "\n```\n",
  );
  assert.equal(text.includes("sandbox_mode"), false);
  assert.ok(text.includes("请把标题改成中文"));
  assert.equal(text.includes("x".repeat(400)), false);
});

function fakePaseoForModel(lastMessage, { ready = true } = {}) {
  const created = [];
  const paseo = {
    config: { get: async () => ({ config: { providers: { cchp: { extends: "codex", label: "CCHP" } } } }) },
    providers: {
      snapshot: async () => ({ entries: ready ? [{
        provider: "cchp",
        status: "ready",
        enabled: true,
        models: [{ id: "m1", label: "M", isDefault: true }],
      }] : [] }),
      listModels: async () => ({ models: [] }),
    },
    workspaces: {
      create: async (options) => {
        created.push(options);
        return {
          agents: {
            create: async (input) => ({
              run: async () => ({ status: "idle", lastMessage }),
              archive: async () => ({}),
              config: input,
            }),
          },
          archive: async () => ({}),
        };
      },
    },
  };
  return { paseo, created };
}

test("manual conversation titles come only from the model, never from a fallback", async () => {
  const { generateConversationTitle, generateTitle } = await import("../server/helper.ts");
  const settings = settingsSchema.parse({});

  const ok = fakePaseoForModel("现在概括会话最近讨论的标题问题");
  const done = await generateConversationTitle(ok.paseo, settings, {
    transcript: "用户：先排查\n\n助手：现在改手动按钮",
    maxChars: 28,
  });
  assert.deepEqual(done, { title: "现在概括会话最近讨论的标题问题" });

  const invalid = fakePaseoForModel("Fix login bug");
  const rejected = await generateConversationTitle(invalid.paseo, settings, {
    transcript: "用户：先排查",
    maxChars: 28,
  });
  assert.equal(rejected.title, null, "a Han-free title is not a fallback success");
  assert.equal(rejected.errorCode, "invalid_title");

  const offline = fakePaseoForModel("随便", { ready: false });
  const unavailable = await generateConversationTitle(offline.paseo, settings, {
    transcript: "用户：先排查",
    maxChars: 28,
  });
  assert.equal(unavailable.title, null);
  assert.equal(unavailable.errorCode, "provider_unavailable");
});

function makeWriteState(workspace, agents) {
  return { workspace: { ...workspace }, agents: agents.map((agent) => ({ ...agent })), writes: [], sessionWrites: [] };
}

function makeWritePaseo(state) {
  return {
    workspaces: {
      ref: (id) => ({
        refresh: async () => (id === state.workspace.id ? { ...state.workspace } : null),
        setTitle: async (title) => {
          state.writes.push(title);
          state.workspace.title = title;
          return { title };
        },
      }),
    },
    agents: {
      ref: (id) => ({
        refresh: async () => {
          const agent = state.agents.find((entry) => entry.id === id);
          return agent ? { agent: { ...agent } } : null;
        },
      }),
    },
  };
}

function writeOptionsFor(state, generateConversation, overrides = {}) {
  return {
    paseo: makeWritePaseo(state),
    settings: settingsSchema.parse({}),
    workspaceId: state.workspace.id,
    // A single eligible session is preselected; each request names one target.
    claims: new Set(),
    agentClaims: new Set(),
    listAgents: async () => state.agents,
    readConversation: async () => ({ text: "用户：合成会话内容", turns: 1 }),
    generateConversation,
    renameSession: async (agentId, title) => {
      const agent = state.agents.find((entry) => entry.id === agentId);
      if (!agent) return { ok: false, failure: "failed" };
      state.sessionWrites.push(title);
      agent.title = title;
      return { ok: true };
    },
    ...overrides,
  };
}

test("consecutive manual requests keep Exa, Keenable, TS and agent-sync and write only their scope", async () => {
  const { generateConversationTitle } = await import("../server/helper.ts");
  const { regenerateWorkspaceTitle } = await import("../server/regenerate.ts");
  const settings = settingsSchema.parse({});

  const answering = (answer) => {
    const helper = fakePaseoForModel(answer);
    return (request, timeoutMs, deadlineAt) =>
      generateConversationTitle(helper.paseo, settings, request, { timeoutMs, deadlineAt });
  };
  const state = makeWriteState(
    {
      id: "w1",
      projectId: "p1",
      projectDisplayName: "Paseo",
      workspaceDirectory: "/synthetic/workspace",
      name: "w1",
      title: "Extend workspace usage plugin",
      background: false,
      metadata: {},
      archivingAt: null,
    },
    [
      { id: "a1", title: "旧会话标题一" },
      { id: "a2", title: "旧会话标题二" },
    ].map((agent) => ({
      ...agent,
      workspaceId: "w1",
      background: false,
      cwd: "/synthetic/workspace",
      labels: {},
      metadata: {},
      lastUserMessageAt: "2026-11-24T00:00:00.000Z",
      createdAt: "2026-11-24T00:00:00.000Z",
      updatedAt: "2026-11-24T00:00:00.000Z",
    })),
  );
  const run = (scope, agentId, answer) => regenerateWorkspaceTitle(writeOptionsFor(state, answering(answer), { scope, agentId }));

  // 1. Both targets: the answer contains two products outside the auto list.
  assert.deepEqual(await run("both", "a1", "对比 Exa 与 Keenable 的检索结果"), {
    status: "done", title: "对比 Exa 与 Keenable 的检索结果",
    workspaceUpdated: true, sessionUpdated: true, agentId: "a1",
  });
  assert.equal(state.workspace.title, "对比 Exa 与 Keenable 的检索结果");
  assert.equal(state.agents[0].title, "对比 Exa 与 Keenable 的检索结果");
  assert.equal(state.agents[1].title, "旧会话标题二");

  // 2. Switch to the other session: only that session changes.
  assert.deepEqual(await run("session", "a2", "排查 TS 类型错误"), {
    status: "done", title: "排查 TS 类型错误",
    workspaceUpdated: false, sessionUpdated: true, agentId: "a2",
  });
  assert.equal(state.workspace.title, "对比 Exa 与 Keenable 的检索结果");
  assert.equal(state.agents[0].title, "对比 Exa 与 Keenable 的检索结果");
  assert.equal(state.agents[1].title, "排查 TS 类型错误");

  // 3. Switch to the workspace: the earlier session writes are left alone.
  assert.deepEqual(await run("workspace", "a2", "整理 agent-sync 提示词与技能"), {
    status: "done", title: "整理 agent-sync 提示词与技能",
    workspaceUpdated: true, sessionUpdated: false, agentId: "a2",
  });
  assert.equal(state.workspace.title, "整理 agent-sync 提示词与技能");
  assert.equal(state.agents[0].title, "对比 Exa 与 Keenable 的检索结果");
  assert.equal(state.agents[1].title, "排查 TS 类型错误");
  assert.deepEqual(state.writes, [
    "对比 Exa 与 Keenable 的检索结果",
    "整理 agent-sync 提示词与技能",
  ]);
  assert.deepEqual(state.sessionWrites, [
    "对比 Exa 与 Keenable 的检索结果",
    "排查 TS 类型错误",
  ]);
});

test("automatic naming still rejects an unknown product token", async () => {
  const { generateTitle } = await import("../server/helper.ts");
  const settings = settingsSchema.parse({});
  const auto = fakePaseoForModel("整理 Exa 提示词");
  const generated = await generateTitle(auto.paseo, settings, {
    kind: "workspace",
    prompt: "整理 Exa 提示词",
    maxChars: 28,
  });
  assert.equal(generated.source, "fallback");
  assert.equal(generated.title, "整理提示词");
  assert.equal(generated.title.includes("Exa"), false);
});

test("automatic first-task naming still returns its Chinese fallback", async () => {
  const { generateTitle } = await import("../server/helper.ts");
  const settings = settingsSchema.parse({});
  const offline = fakePaseoForModel("x", { ready: false });
  const result = await generateTitle(offline.paseo, settings, {
    kind: "workspace",
    prompt: "Fix login bug",
    maxChars: 28,
  });
  assert.equal(result.source, "fallback");
  assert.equal(result.title, "修复登录问题");
  assert.equal(result.errorCode, "provider_unavailable");

  const invalid = fakePaseoForModel("Fix login bug");
  const fallback = await generateTitle(invalid.paseo, settings, {
    kind: "workspace",
    prompt: "Fix login bug",
    maxChars: 28,
  });
  assert.deepEqual(
    { source: fallback.source, title: fallback.title, errorCode: fallback.errorCode },
    { source: "fallback", title: "修复登录问题", errorCode: "model_failed" },
  );
});

test("a real timeline read forwards only visible prose and no credentials", async () => {
  const entries = [
    { type: "user_message", text: "首条任务：排查标题插件，GH_TOKEN=synthetic-token-value", turnId: "t0", timestamp: "2026-11-20T00:00:00Z" },
    { type: "tool_call", text: "TOOL-ARGS-AWSLAMBDA", turnId: "t0", timestamp: "2026-11-20T00:00:01Z" },
    { type: "notification", text: "SYSTEM-NOTICE", turnId: "t0", timestamp: "2026-11-20T00:00:02Z" },
    { type: "assistant_message", text: "看完了插件入口", turnId: "t0", timestamp: "2026-11-20T00:00:03Z" },
    { type: "user_message", text: '现在 {"password":"synthetic-pw-value"} 改成概括会话', turnId: "t1", timestamp: "2026-11-23T00:00:00Z" },
  ];
  const paseo = { agents: { ref: () => ({ timeline: fakeTimeline(entries) }) } };
  const excerpt = await readSessionConversation(paseo, "a1");
  assert.ok(excerpt);
  assert.ok(excerpt.text.includes("首条任务：排查标题插件"));
  assert.ok(excerpt.text.includes("改成概括会话"));
  for (const leaked of ["synthetic-token-value", "synthetic-pw-value", "TOOL-ARGS-AWSLAMBDA", "SYSTEM-NOTICE"]) {
    assert.equal(excerpt.text.includes(leaked), false, `leaked ${leaked}`);
  }
});
