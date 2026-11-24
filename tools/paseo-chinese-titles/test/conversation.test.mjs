import test from "node:test";
import assert from "node:assert/strict";
import {
  buildConversationExcerpt,
  redactSecrets,
  withoutInjectedBlocks,
} from "../shared/transcript.ts";
import { readSessionConversation, readSessionNamingMaterial } from "../server/conversation.ts";
import {
  isSelectableSession,
  resolveSessionSelection,
  selectableSessionsFor,
} from "../shared/session-options.ts";
import { checkConversationSummaryTitle, sanitizeConversationTitle } from "../shared/title.ts";
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

/** The reported failure: five turns on the real work, then nine wrap-up turns. */
function longSessionWithClosing() {
  const entries = [{ type: "user_message", text: "先看报告，找出问题", turnId: "t0" }];
  const work = [
    "报告里的第一个问题：把结论写进提示词规则",
    "第二个问题：把同一要求写进技能规则，比较适用范围",
    "第三个问题：让验收标准和恢复义务对齐",
    "第四个问题：核对跨端同步时的加载边界",
  ];
  work.forEach((text, index) => {
    entries.push({ type: "user_message", text, turnId: `w${index}` });
    entries.push({ type: "assistant_message", text: `已按第 ${index + 1} 项修改规则`, turnId: `w${index}` });
  });
  for (let number = 1; number <= 9; number += 1) {
    entries.push({ type: "user_message", text: `收尾：确认第 ${number} 项 MEMORY.md 存储安排`, turnId: `c${number}` });
    entries.push({ type: "assistant_message", text: `第 ${number} 项确认完毕`, turnId: `c${number}` });
  }
  return entries;
}

test("a closing run of wrap-up turns does not displace the work that ran through the session", () => {
  const excerpt = buildConversationExcerpt(longSessionWithClosing(), { maxChars: 2_400 });
  assert.ok(excerpt.text.includes("先看报告"), "the opening is kept");
  assert.ok(
    /提示词规则|技能规则|验收标准|加载边界/.test(excerpt.text),
    `the middle work must survive the wrap-up: ${excerpt.text}`,
  );
  assert.ok(excerpt.text.includes("MEMORY.md"), "the closing item is still visible as context");
  assert.ok(Array.from(excerpt.text).length <= 2_400);
});

test("a tight budget keeps every turn in order and clips long answers", () => {
  const entries = [{ type: "user_message", text: "贯穿主线：把报告问题落实到提示词与技能", turnId: "t0" }];
  for (let number = 1; number <= 6; number += 1) {
    entries.push({ type: "user_message", text: `第 ${number} 段问题：${["写进提示词", "写进技能", "对齐验收", "核对加载", "补恢复入口", "整理登记"][number - 1]}`, turnId: `u${number}` });
    entries.push({ type: "assistant_message", text: `答复 ${"很长的助手输出".repeat(60)}`, turnId: `u${number}` });
  }
  const excerpt = buildConversationExcerpt(entries, { maxChars: 700 });
  assert.ok(excerpt.text.includes("贯穿主线"), excerpt.text);
  // No turn is sampled away: each question is still there, in its own order.
  const asked = excerpt.text.match(/第 [0-9] 段问题/gu) ?? [];
  assert.deepEqual(asked, ["第 1 段问题", "第 2 段问题", "第 3 段问题", "第 4 段问题", "第 5 段问题", "第 6 段问题"]);
  assert.ok(Array.from(excerpt.text).length <= 700);
});

test("a long conversation keeps its chronological order under a tight budget", () => {
  const entries = [];
  for (let index = 0; index < 40; index += 1) {
    entries.push({ type: "user_message", text: `第 ${index} 轮：中间话题 ${"细节".repeat(60)}`, turnId: `t${index}` });
    entries.push({ type: "assistant_message", text: `第 ${index} 轮答复 ${"说明".repeat(60)}`, turnId: `t${index}` });
  }
  const excerpt = buildConversationExcerpt(entries, { maxChars: 900 });
  assert.ok(excerpt.text.includes("第 0 轮"), excerpt.text.slice(0, 120));
  assert.ok(excerpt.text.includes("第 39 轮"), "the newest turn must survive");
  // Every round appears in ascending order: this is a clipped contiguous read,
  // not a sample that jumps around.
  const rounds = [...excerpt.text.matchAll(/第 ([0-9]+) 轮/g)].map((match) => Number(match[1]));
  const unique = [...new Set(rounds)];
  assert.deepEqual(unique, [...unique].sort((left, right) => left - right));
  assert.ok(Array.from(excerpt.text).length <= 900);
});

test("a short session is passed through nearly verbatim", () => {
  const excerpt = buildConversationExcerpt([
    { type: "user_message", text: "把中文标题按钮放到工作区菜单里", turnId: "s1" },
    { type: "assistant_message", text: "已加头部按钮，点开中文标题面板。", turnId: "s1" },
    { type: "user_message", text: "再补一个回归用例", turnId: "s2" },
  ]);
  assert.ok(excerpt.text.includes("把中文标题按钮放到工作区菜单里"), excerpt.text);
  assert.ok(excerpt.text.includes("已加头部按钮，点开中文标题面板。"), excerpt.text);
  assert.ok(excerpt.text.includes("再补一个回归用例"), excerpt.text);
  assert.equal(excerpt.text.includes("…"), false, "a short session is not clipped");
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
  assert.deepEqual(buildConversationExcerpt([]), {
    text: "",
    turns: 0,
    segments: [],
    coveredTurns: 0,
    coverage: { kind: "full" },
  });
  assert.deepEqual(
    buildConversationExcerpt([{ type: "reasoning", text: "only thinking" }]),
    { text: "", turns: 0, segments: [], coveredTurns: 0, coverage: { kind: "full" } },
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

test("a long session reads its real first task, a mid-session point and its newest work", async () => {
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

test("a tool-dense session still reaches its opening and its newest work", async () => {
  // Only the first turn and the last turn carry conversation; everything in
  // between is tool traffic. A tail-only read would see the closing lines and
  // a head-only read would see the opening, but the summary needs both.
  const entries = [{ type: "user_message", text: "开场主题：报告问题如何落实到提示词和技能", turnId: "t0", timestamp: "2026-11-20T00:00:00Z" }];
  for (let index = 0; index < 400; index += 1) {
    entries.push({ type: "tool_call", text: `TOOL-STEP-${index}`, turnId: `x${index}`, timestamp: "2026-11-21T00:00:00Z" });
  }
  entries.push({ type: "user_message", text: "结尾：确认 Memory 存储安排", turnId: "t1", timestamp: "2026-11-23T00:00:00Z" });
  const directions = [];
  const timeline = fakeTimeline(entries);
  const counted = {
    refetch: async (options = {}) => {
      directions.push(options.direction ?? "tail");
      return timeline.refetch(options);
    },
  };
  const excerpt = await readSessionConversation({ agents: { ref: () => ({ timeline: counted }) } }, "a1");
  assert.ok(excerpt);
  assert.ok(excerpt.text.includes("开场主题"), excerpt.text);
  assert.ok(excerpt.text.includes("结尾：确认 Memory"), excerpt.text);
  assert.equal(directions[0], "after", "the scan starts at the opening");
  assert.equal(directions.every((direction) => direction === "after"), true, directions.join(","));
  assert.equal(excerpt.coverage.kind, "full", "a 402-row session is fully read within the caps");
});

test("a page without a cursor stops only its own side and keeps the other side's content", async () => {
  // The tail says hasOlder=true but returns no startCursor. That is not proof
  // the timeline start was reached, so the head scan's opening must survive.
  const entries = [{ type: "user_message", text: "开场：先看报告", turnId: "t0" }];
  for (let index = 0; index < 300; index += 1) {
    entries.push({ type: "tool_call", text: `TOOL-${index}`, turnId: `x${index}` });
  }
  entries.push({ type: "user_message", text: "结尾：确认收尾", turnId: "t1" });
  const base = fakeTimeline(entries);
  const skewed = {
    refetch: async (options = {}) => {
      const result = await base.refetch(options);
      if (options.direction === "tail" || (options.direction ?? "tail") === "tail") {
        return { ...result, hasOlder: true, startCursor: null };
      }
      return result;
    },
  };
  const excerpt = await readSessionConversation({ agents: { ref: () => ({ timeline: skewed }) } }, "a1");
  assert.ok(excerpt);
  assert.ok(excerpt.text.includes("开场：先看报告"), `the head read must not be discarded: ${excerpt.text}`);
});

test("a short session is read in one chronological forward page", async () => {
  const entries = [];
  for (let index = 0; index < 5; index += 1) {
    entries.push({ type: "user_message", text: `短会话第 ${index} 轮`, turnId: `s${index}` });
    entries.push({ type: "assistant_message", text: `短会话答复 ${index}`, turnId: `s${index}` });
  }
  const directions = [];
  const timeline = fakeTimeline(entries);
  const counted = {
    refetch: async (options = {}) => {
      directions.push(options.direction ?? "tail");
      return timeline.refetch(options);
    },
  };
  const excerpt = await readSessionConversation({ agents: { ref: () => ({ timeline: counted }) } }, "a1");
  assert.ok(excerpt);
  assert.deepEqual(directions, ["after"], "a short session is read with exactly one forward page");
  assert.equal(excerpt.coverage.kind, "full");
});

test("the reported 14-turn session keeps the main thread above the closing item", async () => {
  const entries = [{ type: "user_message", text: "先看报告", turnId: "t0" }];
  const work = [
    "报告里第一个问题：要怎么改",
    "把结论写进提示词规则",
    "把同一要求写进技能规则，比较适用范围",
    "对齐验收标准和恢复义务",
  ];
  work.forEach((text, index) => {
    entries.push({ type: "user_message", text, turnId: `w${index}` });
    entries.push({ type: "assistant_message", text: `处理第 ${index + 1} 项`, turnId: `w${index}` });
  });
  for (let number = 1; number <= 9; number += 1) {
    entries.push({ type: "user_message", text: `收尾：确认第 ${number} 项 MEMORY.md 存储安排`, turnId: `c${number}` });
  }
  const excerpt = await readSessionConversation({ agents: { ref: () => ({ timeline: fakeTimeline(entries) }) } }, "a1");
  assert.ok(excerpt);
  assert.ok(excerpt.text.includes("先看报告"), excerpt.text);
  assert.ok(excerpt.text.includes("提示词规则"), `the main thread's prompt rule must survive: ${excerpt.text}`);
  assert.ok(excerpt.text.includes("技能规则"), `the main thread's skill rule must survive: ${excerpt.text}`);
  assert.ok(excerpt.text.includes("MEMORY.md"), "the closing item is still present as context");
});

test("the prompt asks for the through-line and does not let the last turn take over", async () => {
  const { CONVERSATION_PROMPT, conversationPrompt } = await import("../server/helper.ts");
  assert.ok(CONVERSATION_PROMPT.includes("whole conversation"), CONVERSATION_PROMPT);
  assert.ok(/runs through/.test(CONVERSATION_PROMPT), CONVERSATION_PROMPT);
  assert.ok(/wrap-up/.test(CONVERSATION_PROMPT), CONVERSATION_PROMPT);
  assert.ok(/genuine topic change/.test(CONVERSATION_PROMPT), CONVERSATION_PROMPT);
  assert.equal(CONVERSATION_PROMPT.includes("MEMORY"), false, "no domain term is hard-coded");

  // The per-request user prompt weighs the whole conversation rather than the tail.
  const prompt = conversationPrompt({ transcript: "用户：合成", maxChars: 28 });
  assert.ok(/whole conversation/.test(prompt), prompt);
  assert.ok(prompt.includes("用户：合成"), "the excerpt is carried verbatim");
});

test("the excerpt that reaches the helper carries the opening, middle and closing", async () => {
  const { generateConversationTitle } = await import("../server/helper.ts");
  const settings = settingsSchema.parse({});
  const entries = [{ type: "user_message", text: "先看报告", turnId: "t0" }];
  for (let index = 1; index <= 4; index += 1) {
    entries.push({ type: "user_message", text: `第 ${index} 个问题：写进提示词或技能规则`, turnId: `w${index}` });
    entries.push({ type: "assistant_message", text: `已处理 ${index}`, turnId: `w${index}` });
  }
  for (let number = 1; number <= 9; number += 1) {
    entries.push({ type: "user_message", text: `收尾：确认第 ${number} 项 MEMORY.md 存储安排`, turnId: `c${number}` });
  }
  const excerpt = await readSessionConversation({ agents: { ref: () => ({ timeline: fakeTimeline(entries) }) } }, "a1");
  assert.ok(excerpt);
  let seenPrompt = "";
  const paseo = {
    config: { get: async () => ({ config: { providers: { cchp: { extends: "codex", label: "CCHP" } } } }) },
    providers: {
      snapshot: async () => ({ entries: [{ provider: "cchp", status: "ready", enabled: true, models: [{ id: "m1", label: "M", isDefault: true }] }] }),
      listModels: async () => ({ models: [] }),
    },
    workspaces: {
      create: async () => ({
        agents: {
          create: async () => ({
            run: async (prompt) => {
              seenPrompt = prompt;
              return { status: "idle", lastMessage: "整理报告问题到提示词与技能" };
            },
            archive: async () => ({}),
          }),
        },
        archive: async () => ({}),
      }),
    },
  };
  const result = await generateConversationTitle(paseo, settings, { transcript: excerpt.text, maxChars: 28 });
  assert.deepEqual(result, { title: "整理报告问题到提示词与技能" });
  assert.ok(seenPrompt.includes("先看报告"), "the opening reaches the helper");
  assert.ok(/提示词或技能规则/.test(seenPrompt), "the middle reaches the helper");
  assert.ok(seenPrompt.includes("MEMORY.md"), "the closing is present as context");
});

test("a 30k read that fits two model segments is never reported as segment-capped", async () => {
  // 24 readable turns of ~1 200 characters each: inside the 30 000-character
  // read budget, but more than one model input if the parts were small.
  const entries = [];
  for (let index = 0; index < 24; index += 1) {
    entries.push({ type: "user_message", text: `第 ${index} 轮问题 ${"甲".repeat(400)}`, turnId: `t${index}` });
    entries.push({ type: "assistant_message", text: `第 ${index} 轮答复 ${"乙".repeat(700)}`, turnId: `t${index}` });
  }
  const excerpt = await readSessionConversation({ agents: { ref: () => ({ timeline: fakeTimeline(entries) }) } }, "a1");
  assert.ok(excerpt);
  assert.equal(excerpt.coverage.kind, "full", JSON.stringify(excerpt.coverage));
  assert.equal(excerpt.coveredTurns, excerpt.turns);
  assert.ok(excerpt.segments.length <= 2, `segments: ${excerpt.segments.length}`);
  assert.ok(excerpt.text.includes("第 0 轮问题") && excerpt.text.includes("第 23 轮答复"));
});

test("a read inside the char budget but past the segment budget is reported as segment-capped", async () => {
  // 40 turns of 747 characters are 29 880 characters of visible text, just under
  // the 30 000 read cap, but the "用户：" labels push the transcript past the two
  // 15 000-character model segments. That must be reported, not hidden.
  const entries = Array.from({ length: 40 }, (_, index) => ({
    type: "user_message",
    text: `第 ${index} 轮 ${"细".repeat(740)}`,
    turnId: `t${index}`,
  }));
  const excerpt = await readSessionConversation({ agents: { ref: () => ({ timeline: fakeTimeline(entries) }) } }, "a1");
  assert.ok(excerpt);
  assert.equal(excerpt.coverage.kind, "partial");
  assert.equal(excerpt.coverage.reason, "segment_cap");
  assert.ok(excerpt.coveredTurns < excerpt.turns, "the uncovered turns are counted, never claimed");
});

test("a cursor reset or sequence gap is reported as partial, never as full coverage", async () => {
  const entries = [{ type: "user_message", text: "开场：先查 Codex 连接", turnId: "t0" }];
  for (let index = 0; index < 400; index += 1) {
    entries.push({ type: "tool_call", text: `TOOL-${index}`, turnId: `x${index}` });
  }
  entries.push({ type: "user_message", text: "结尾：停用 CCHP", turnId: "t1" });
  const base = fakeTimeline(entries);
  // Paseo 0.17.4 answers a stale cursor or a gap by refetching the tail, so the
  // page is not the next 100 rows: it jumps forward and can end hasNewer:false.
  const jumpToTail = async (options) => {
    const tail = await base.refetch({ ...options, direction: "tail" });
    return { ...tail, reset: true, staleCursor: true, gap: false, hasNewer: false };
  };
  let calls = 0;
  const resetting = {
    refetch: async (options = {}) => {
      calls += 1;
      if (calls === 2) return jumpToTail(options);
      return base.refetch(options);
    },
  };
  const excerpt = await readSessionConversation({ agents: { ref: () => ({ timeline: resetting }) } }, "a1");
  assert.ok(excerpt);
  assert.equal(excerpt.coverage.kind, "partial");
  assert.equal(excerpt.coverage.reason, "reset");
  assert.ok(excerpt.text.includes("开场：先查 Codex 连接"), "the pages read before the reset are kept");
  assert.equal(excerpt.text.includes("结尾：停用 CCHP"), false, "a page that jumped ahead is not joined onto the earlier read");

  const gapPage = async (options) => {
    const tail = await base.refetch({ ...options, direction: "tail" });
    return { ...tail, reset: true, staleCursor: false, gap: true, hasNewer: false };
  };
  let first = true;
  const gapAfterFirst = {
    refetch: async (options = {}) => {
      if (first) { first = false; return base.refetch(options); }
      return gapPage(options);
    },
  };
  // A reset on the very first request is a discontinuity too: earlier items
  // may already be gone, so the tail page is all that is readable and it is
  // reported as partial rather than as the whole conversation.
  const firstPageReset = {
    refetch: async (options = {}) => jumpToTail(options),
  };
  const firstReset = await readSessionConversation({ agents: { ref: () => ({ timeline: firstPageReset }) } }, "a1");
  assert.ok(firstReset);
  assert.equal(firstReset.coverage.kind, "partial");
  assert.equal(firstReset.coverage.reason, "reset");
  assert.equal(firstReset.text.includes("开场：先查 Codex 连接"), false, "the lost opening is not invented");
  assert.ok(firstReset.text.includes("结尾：停用 CCHP"), "a first-page reset keeps the tail it was actually served");

  const gapExcerpt = await readSessionConversation({ agents: { ref: () => ({ timeline: gapAfterFirst }) } }, "a1");
  assert.ok(gapExcerpt);
  assert.equal(gapExcerpt.coverage.kind, "partial");
  assert.equal(gapExcerpt.coverage.reason, "gap");
  assert.equal(gapExcerpt.text.includes("结尾：停用 CCHP"), false, "a gap never borrows the post-gap tail");
});

test("session naming material gives up on a discontinuous page instead of using mid-session text", async () => {
  const entries = [
    { type: "user_message", text: "真正的首问：排查标题插件", turnId: "t0" },
    { type: "assistant_message", text: "先看插件入口和 hook。", turnId: "t0" },
    { type: "user_message", text: "会话中段：换成 WebSocket 排查", turnId: "t9" },
    { type: "assistant_message", text: "中段答复，不是命名素材。", turnId: "t9" },
  ];
  // Control: an ordinary head page yields the real first question and answer.
  const ok = await readSessionNamingMaterial(
    { agents: { ref: () => ({ timeline: fakeTimeline(entries) }) } },
    "a1",
    { turnId: "t9" },
  );
  // The question is the session's first one; the answer belongs to the turn
  // that triggered naming, which here is the later completed turn.
  assert.equal(ok?.question, "真正的首问：排查标题插件");
  assert.equal(ok?.answer, "中段答复，不是命名素材。");

  // Paseo 0.17.4 can answer even the first request with a stale-cursor tail.
  // The first row is then mid-session, so no naming material may be produced.
  const resetting = {
    refetch: async (options = {}) => ({
      ...(await fakeTimeline(entries).refetch(options)),
      reset: true,
      staleCursor: true,
      gap: false,
      hasNewer: false,
    }),
  };
  const material = await readSessionNamingMaterial(
    { agents: { ref: () => ({ timeline: resetting }) } },
    "a1",
    { turnId: "t9" },
  );
  assert.equal(material, null, "a mid-session tail is never the session's opening");
});

test("a first-page transport failure is a read failure, not an empty conversation", async () => {
  const throwing = {
    agents: {
      ref: () => ({
        timeline: {
          refetch: async () => {
            throw new Error("socket closed");
          },
        },
      }),
    },
  };
  assert.equal(await readSessionConversation(throwing, "a1"), null);
});
test("a failed later page keeps the bounded content already read", async () => {
  const entries = [{ type: "user_message", text: "开场：先看报告", turnId: "t0" }];
  for (let index = 0; index < 400; index += 1) {
    entries.push({ type: "tool_call", text: `TOOL-${index}`, turnId: `x${index}` });
  }
  entries.push({ type: "user_message", text: "结尾：补一个回归", turnId: "t1" });
  const base = fakeTimeline(entries);
  let calls = 0;
  const flaky = {
    refetch: async (options = {}) => {
      calls += 1;
      if (calls === 2) return { error: "transport failed", entries: [] };
      return base.refetch(options);
    },
  };
  const excerpt = await readSessionConversation({ agents: { ref: () => ({ timeline: flaky }) } }, "a1");
  assert.ok(excerpt, "a later-page failure still yields the first page's content");
  assert.ok(excerpt.text.includes("开场：先看报告") || excerpt.text.includes("结尾：补一个回归"), excerpt.text);
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

/** Scenario A: Codex WebSocket, CCHP upstream WebSocket, HTTP fallback, then a final stop action. */
function codexConnectionSession() {
  const entries = [
    { type: "user_message", text: "先查一下这个会话里 Codex 为什么走 WebSocket，而不是普通的请求响应", turnId: "q0" },
    { type: "assistant_message", text: "原因是 Paseo 客户端与会话服务之间保持了长连接，事件和审批都从这条连接推送。", turnId: "q0" },
    { type: "user_message", text: "那 CCHP 上游是不是也走 WebSocket", turnId: "q1" },
    { type: "assistant_message", text: "CCHP 上游确实另有一条 WebSocket 连接，负责把执行事件转回 daemon。", turnId: "q1" },
    { type: "user_message", text: "如果上游连不上，会不会自动回退到 HTTP", turnId: "q2" },
    { type: "assistant_message", text: "会先尝试 WebSocket，握手失败时回退到 HTTP 轮询，日志里能看到两条路径。", turnId: "q2" },
  ];
  // A long stretch of tool traffic and wrap-up chatter after the real work.
  for (let index = 0; index < 30; index += 1) {
    entries.push({ type: "tool_call", text: `TOOL-${index}`, turnId: `x${index}` });
  }
  for (let index = 0; index < 6; index += 1) {
    entries.push({ type: "user_message", text: `收尾第 ${index} 项：再确认一下清单`, turnId: `c${index}` });
    entries.push({ type: "assistant_message", text: `收尾第 ${index} 项已确认`, turnId: `c${index}` });
  }
  entries.push({ type: "user_message", text: "最后一步：执行停用 CCHP/GDR", turnId: "last" });
  entries.push({ type: "assistant_message", text: "已停用 CCHP 和 GDR 两个 provider。", turnId: "last" });
  return entries;
}

test("scenario A: the whole thread reaches the model, the final stop action does not replace it", async () => {
  const paseo = { agents: { ref: () => ({ timeline: fakeTimeline(codexConnectionSession()) }) } };
  const excerpt = await readSessionConversation(paseo, "a1");
  assert.ok(excerpt);
  assert.equal(excerpt.coverage.kind, "full");
  for (const evidence of ["Codex 为什么走 WebSocket", "CCHP 上游确实另有一条 WebSocket", "回退到 HTTP 轮询"]) {
    assert.ok(excerpt.text.includes(evidence), `${evidence} must reach the model: ${excerpt.text.slice(0, 200)}`);
  }
  assert.ok(excerpt.text.includes("最后一步：执行停用 CCHP/GDR"), "the last action is context, not the topic");
  // Chronological order: the evidence appears before the closing stop action.
  assert.ok(
    excerpt.text.indexOf("回退到 HTTP 轮询") < excerpt.text.indexOf("最后一步：执行停用 CCHP/GDR"),
    "the thread keeps its original order",
  );
  const { conversationPrompt } = await import("../server/helper.ts");
  const prompt = conversationPrompt({ transcript: excerpt.text, maxChars: 28 });
  assert.ok(prompt.includes("第 0 段") === false);
  assert.ok(prompt.includes("最后一步：执行停用 CCHP/GDR"));
  assert.ok(prompt.includes("<environment_context>") === false);
});

test("scenario A: a long thread is condensed part by part and every part reaches the final title call", async () => {
  const { generateConversationTitle } = await import("../server/helper.ts");
  const settings = settingsSchema.parse({});
  const segments = [
    "用户：先查 Codex 为什么走 WebSocket\n助手：因为用了长连接",
    "用户：那 CCHP 上游呢\n助手：上游也有一条 WebSocket",
    "用户：连不上会回退 HTTP 吗\n助手：会回退到 HTTP 轮询",
    "用户：最后停用 CCHP/GDR\n助手：已停用",
  ];
  const prompts = [];
  const answers = ["段一：查清 Codex 长连接原因", "段二：确认 CCHP 上游 WebSocket", "段三：确认 HTTP 回退", "段四：停用 CCHP/GDR"];
  const paseo = fakePaseoForModel("", { sequence: [...answers, "排查 Codex 连接方式与 HTTP 回退"] }).paseo;
  const originalCreate = paseo.workspaces.create;
  paseo.workspaces.create = async (options) => {
    const workspace = await originalCreate(options);
    const originalAgents = workspace.agents.create;
    workspace.agents.create = async (input) => {
      const agent = await originalAgents(input);
      const originalRun = agent.run;
      agent.run = async (prompt, runOptions) => {
        prompts.push(prompt);
        return originalRun(prompt, runOptions);
      };
      return agent;
    };
    return workspace;
  };
  const result = await generateConversationTitle(paseo, settings, { transcript: segments.join("\n\n"), segments, maxChars: 28 });
  assert.equal(result.title, "排查 Codex 连接方式与 HTTP 回退");
  assert.deepEqual(result.segments, { total: 4, used: 4 });
  assert.equal(prompts.length, 5, "four part digests plus one final title call");
  const markers = ["先查 Codex 为什么走 WebSocket", "CCHP 上游", "回退 HTTP", "停用 CCHP/GDR"];
  for (let index = 0; index < 4; index += 1) {
    assert.ok(prompts[index].includes(`Condense part ${index + 1} of 4`), prompts[index].slice(0, 120));
    assert.ok(prompts[index].includes(markers[index]), `segment ${index + 1} reached the model`);
  }
  const finalPrompt = prompts[4];
  for (const digest of answers) assert.ok(finalPrompt.includes(digest), `digest missing: ${digest}`);
  assert.ok(finalPrompt.includes("第 1 段") && finalPrompt.includes("第 4 段"), "order is preserved");
});

test("scenario A: one failed part reports no title instead of claiming a whole-session summary", async () => {
  const { generateConversationTitle } = await import("../server/helper.ts");
  const settings = settingsSchema.parse({});
  const segments = ["用户：一", "用户：二", "用户：三"];
  const paseo = fakePaseoForModel("", { sequence: ["段一", "段二"] }).paseo;
  const result = await generateConversationTitle(paseo, settings, { transcript: segments.join("\n\n"), segments, maxChars: 28 });
  assert.equal(result.title, null);
  assert.equal(result.errorCode, "model_failed");
  assert.deepEqual(result.segments, { total: 3, used: 2 });
});

function fakePaseoForModel(lastMessage, { ready = true, sequence = null } = {}) {
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
              run: async () => {
                // A sequence lets a multi-step helper return one answer per turn.
                const answer = sequence && sequence.length > 0 ? sequence.shift() : lastMessage;
                return { status: "idle", lastMessage: answer };
              },
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

test("the formal entry never accepts the 23-character half-phrase", () => {
  // The reported failure: the stored title was this model answer sliced at 28
  // characters, ending on 的 with its main object gone.
  const raw = "诊断 422 后关闭 CCHP 与 GDR 的 WebSocket";
  const broken = "诊断 422 后关闭 CCHP 与 GDR 的";
  assert.equal(Array.from(broken).length, 23);

  // Over the limit, so the formal entry asks for one semantic shortening
  // rather than writing a hard cut.
  assert.deepEqual(checkConversationSummaryTitle(raw, 28), { kind: "rewrite", reason: "too_long" });
  // A short answer that is itself a truncated phrase is rewritten too, at the
  // 的 that has no lexical reading here.
  assert.deepEqual(
    checkConversationSummaryTitle(broken, 28),
    { kind: "rewrite", reason: "incomplete" },
  );
  // A Latin token followed by an isolated particle cannot be a Chinese word.
  assert.equal(checkConversationSummaryTitle("诊断 CCHP 与", 28).reason, "incomplete");

  // A complete title with the central object is accepted as-is.
  assert.deepEqual(
    checkConversationSummaryTitle("排查 CCHP 与 GDR 的 WebSocket", 28),
    { kind: "ok", title: "排查 CCHP 与 GDR 的 WebSocket" },
  );
  assert.equal(checkConversationSummaryTitle("Fix login bug", 28).kind, "invalid");
  // The automatic path keeps the hard cut of the previous deployed version
  // unchanged; only the formal manual entry is strict about this shape.
  assert.equal(sanitizeConversationTitle(raw, 28), broken);
});

test("complete short titles ending on a normal word are not rewritten", () => {
  // Real titles reported as false positives: 地/得/和 are ordinary word endings.
  for (const title of ["数据库备份迁移到本地", "分析模型输出趋于饱和", "计算个税应纳税所得"]) {
    assert.deepEqual(checkConversationSummaryTitle(title, 28), { kind: "ok", title }, title);
  }
  // Lexicalised 的-words end the same way and are complete phrases.
  for (const title of ["确认本次迁移目的", "核对接口调用标的"]) {
    assert.deepEqual(checkConversationSummaryTitle(title, 28), { kind: "ok", title }, title);
  }
  // A plain 的 at the end without a lexical reading keeps the rewrite verdict.
  assert.equal(checkConversationSummaryTitle("诊断 422 后关闭 CCHP 与 GDR 的", 28).reason, "incomplete");
});

test("several complete short titles each need exactly one model call", async () => {
  const { generateConversationTitle } = await import("../server/helper.ts");
  const settings = settingsSchema.parse({});
  for (const title of ["数据库备份迁移到本地", "分析模型输出趋于饱和", "计算个税应纳税所得"]) {
    const fake = fakePaseoForModel(title);
    let calls = 0;
    const originalCreate = fake.paseo.workspaces.create;
    fake.paseo.workspaces.create = async (options) => {
      const workspace = await originalCreate(options);
      const originalAgents = workspace.agents.create;
      workspace.agents.create = async (input) => {
        const agent = await originalAgents(input);
        const originalRun = agent.run;
        agent.run = async (prompt, runOptions) => {
          calls += 1;
          return originalRun(prompt, runOptions);
        };
        return agent;
      };
      return workspace;
    };
    const result = await generateConversationTitle(fake.paseo, settings, {
      transcript: `用户：${title}\n助手：已处理完毕`,
      maxChars: 28,
    });
    assert.deepEqual(result, { title }, title);
    assert.equal(calls, 1, `${title}: no shortening turn`);
  }
});

test("a complete short manual title needs exactly one model call", async () => {
  const { generateConversationTitle } = await import("../server/helper.ts");
  const settings = settingsSchema.parse({});
  const fake = fakePaseoForModel("排查 CCHP 与 GDR 的 WebSocket");
  const runs = [];
  const originalCreate = fake.paseo.workspaces.create;
  fake.paseo.workspaces.create = async (options) => {
    const workspace = await originalCreate(options);
    const originalAgents = workspace.agents.create;
    workspace.agents.create = async (input) => {
      const agent = await originalAgents(input);
      const originalRun = agent.run;
      agent.run = async (prompt, runOptions) => {
        runs.push(prompt);
        return originalRun(prompt, runOptions);
      };
      return agent;
    };
    return workspace;
  };
  const result = await generateConversationTitle(fake.paseo, settings, {
    transcript: "用户：诊断 422\n助手：上游 WebSocket 402 后停用 CCHP 与 GDR",
    maxChars: 28,
  });
  assert.deepEqual(result, { title: "排查 CCHP 与 GDR 的 WebSocket" });
  assert.equal(runs.length, 1, "a valid title is not sent back for shortening");
});

test("an over-long manual title gets one semantic shortening that keeps the subject", async () => {
  const { generateConversationTitle } = await import("../server/helper.ts");
  const settings = settingsSchema.parse({});
  const long = "诊断 422 后关闭 CCHP 与 GDR 的 WebSocket 长连接并复核偶数";
  const fake = fakePaseoForModel("", { sequence: [long, "排查 CCHP 与 GDR 的 WebSocket"] });
  const runs = [];
  const originalCreate = fake.paseo.workspaces.create;
  fake.paseo.workspaces.create = async (options) => {
    const workspace = await originalCreate(options);
    const originalAgents = workspace.agents.create;
    workspace.agents.create = async (input) => {
      const agent = await originalAgents(input);
      const originalRun = agent.run;
      agent.run = async (prompt, runOptions) => {
        runs.push(prompt);
        return originalRun(prompt, runOptions);
      };
      return agent;
    };
    return workspace;
  };
  const result = await generateConversationTitle(fake.paseo, settings, {
    transcript: "用户：诊断 422\n助手：上游 WebSocket 422 后停用 CCHP 与 GDR",
    maxChars: 28,
  });
  assert.deepEqual(result, { title: "排查 CCHP 与 GDR 的 WebSocket" });
  assert.equal(runs.length, 2, "exactly one shortening turn in the same helper session");
  assert.ok(runs[1].includes("at most 28 characters"), runs[1]);
  assert.ok(runs[1].includes("central technical subject"), runs[1]);
  assert.ok(runs[1].includes(long), "the shortening turn sees the rejected title");
});

test("a shortening turn that still fails writes nothing and does not loop", async () => {
  const { generateConversationTitle } = await import("../server/helper.ts");
  const settings = settingsSchema.parse({});
  const tooLong = "诊断 422 后关闭 CCHP 与 GDR 的 WebSocket 长连接并复核偶数";
  for (const [second, expected] of [
    [tooLong, "rewrite_failed"],
    ["Fix login bug", "invalid_title"],
  ]) {
    const fake = fakePaseoForModel("", { sequence: [tooLong, second] });
    let calls = 0;
    const originalCreate = fake.paseo.workspaces.create;
    fake.paseo.workspaces.create = async (options) => {
      const workspace = await originalCreate(options);
      const originalAgents = workspace.agents.create;
      workspace.agents.create = async (input) => {
        const agent = await originalAgents(input);
        const originalRun = agent.run;
        agent.run = async (prompt, runOptions) => {
          calls += 1;
          return originalRun(prompt, runOptions);
        };
        return agent;
      };
      return workspace;
    };
    const result = await generateConversationTitle(fake.paseo, settings, {
      transcript: "用户：诊断 422\n助手：停用 CCHP 与 GDR",
      maxChars: 28,
    });
    assert.equal(result.title, null, `${expected}: no title is written`);
    assert.equal(result.errorCode, expected);
    assert.equal(calls, 2, `${expected}: one shortening attempt at most`);
  }
});

test("no budget for a shortening turn means timeout and no write", async () => {
  const { generateConversationTitle } = await import("../server/helper.ts");
  const settings = settingsSchema.parse({});
  const tooLong = "诊断 422 后关闭 CCHP 与 GDR 的 WebSocket 长连接并复核偶数";
  const realNow = Date.now;
  const fake = fakePaseoForModel("", { sequence: [tooLong, "不该发出的缩写"] });
  let calls = 0;
  const originalCreate = fake.paseo.workspaces.create;
  fake.paseo.workspaces.create = async (options) => {
    const workspace = await originalCreate(options);
    const originalAgents = workspace.agents.create;
    workspace.agents.create = async (input) => {
      const agent = await originalAgents(input);
      const originalRun = agent.run;
      agent.run = async (prompt, runOptions) => {
        calls += 1;
        if (calls === 1) Date.now = () => realNow() + 17_000;
        return originalRun(prompt, runOptions);
      };
      return agent;
    };
    return workspace;
  };
  let result;
  try {
    result = await generateConversationTitle(fake.paseo, settings, {
      transcript: "用户：诊断 422\n助手：停用 CCHP 与 GDR",
      maxChars: 28,
    }, { deadlineAt: realNow() + 18_000 });
  } finally {
    Date.now = realNow;
  }
  assert.equal(result.title, null);
  assert.equal(result.errorCode, "timeout");
  assert.equal(calls, 1, "an expired budget never starts the shortening turn");
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

test("session naming reads the first question and the answer of the completed turn", async () => {
  const entries = [
    { type: "user_message", text: "先看 Codex 为什么走 WebSocket", turnId: "t1", timestamp: "2026-11-24T00:00:00Z" },
    { type: "tool_call", text: "TOOL-1", turnId: "t1", timestamp: "2026-11-24T00:00:01Z" },
    { type: "assistant_message", text: "因为客户端与会话服务之间要保持长连接。", turnId: "t1", timestamp: "2026-11-24T00:00:02Z" },
    { type: "user_message", text: "那 CCHP 上游呢", turnId: "t2", timestamp: "2026-11-24T00:00:03Z" },
  ];
  const paseo = { agents: { ref: () => ({ timeline: fakeTimeline(entries) }) } };
  const material = await readSessionNamingMaterial(paseo, "a1", { turnId: "t1" });
  assert.deepEqual(material, {
    question: "先看 Codex 为什么走 WebSocket",
    answer: "因为客户端与会话服务之间要保持长连接。",
    turnId: "t1",
  });

  // The next refetch must not be needed: the first question already has its answer.
  const stopped = await readSessionNamingMaterial(paseo, "a1");
  assert.equal(stopped.question, "先看 Codex 为什么走 WebSocket");
  assert.equal(stopped.answer, "因为客户端与会话服务之间要保持长连接。");
});

test("session naming yields no answer for a tool-only or failed turn", async () => {
  const entries = [
    { type: "user_message", text: "先看 Codex 为什么走 WebSocket", turnId: "t1" },
    { type: "tool_call", text: "TOOL-1", turnId: "t1" },
  ];
  const paseo = { agents: { ref: () => ({ timeline: fakeTimeline(entries) }) } };
  const material = await readSessionNamingMaterial(paseo, "a1", { turnId: "t1" });
  assert.equal(material.question, "先看 Codex 为什么走 WebSocket");
  assert.equal(material.answer, null);
});

test("a tool-dense opening still yields the first question and the completed answer", async () => {
  // 700 tool rows sit between the question and its answer: more than the
  // forward scan's 400-visible-entry budget can walk. The answer is recovered
  // by one bounded tail read of the completed turn, never guessed.
  const entries = [{ type: "user_message", text: "先看 Codex 为什么走 WebSocket", turnId: "t1" }];
  for (let index = 0; index < 700; index += 1) {
    entries.push({ type: "user_message", text: `阶段 ${index} 继续核对`, turnId: `n${index}` });
    entries.push({ type: "assistant_message", text: `阶段 ${index} 已核对`, turnId: `n${index}` });
  }
  entries.push({ type: "assistant_message", text: "Codex 与 daemon 之间保持 WebSocket 长连接。", turnId: "t1" });
  const directions = [];
  const base = fakeTimeline(entries);
  const counted = {
    refetch: async (options = {}) => {
      directions.push(options.direction ?? "tail");
      return base.refetch(options);
    },
  };
  const paseo = { agents: { ref: () => ({ timeline: counted }) } };
  const material = await readSessionNamingMaterial(paseo, "a1", { turnId: "t1" });
  assert.ok(material);
  assert.equal(material.question, "先看 Codex 为什么走 WebSocket");
  assert.equal(material.answer, "Codex 与 daemon 之间保持 WebSocket 长连接。");
  assert.ok(directions.includes("tail"), "the fallback read targets the newest turn");
});

test("every assistant part of the completed turn is naming material", async () => {
  const entries = [
    { type: "user_message", text: "先看 Codex 为什么走 WebSocket", turnId: "t1" },
    { type: "assistant_message", text: "先说明一下，我分两部分回答。", turnId: "t1" },
    { type: "tool_call", text: "TOOL-1", turnId: "t1" },
    { type: "assistant_message", text: "结论是客户端与 daemon 之间保持 WebSocket 长连接。", turnId: "t1" },
    { type: "user_message", text: "那 CCHP 上游呢", turnId: "t2" },
    { type: "assistant_message", text: "上游也有 WebSocket。", turnId: "t2" },
  ];
  const paseo = { agents: { ref: () => ({ timeline: fakeTimeline(entries) }) } };
  const material = await readSessionNamingMaterial(paseo, "a1", { turnId: "t1" });
  assert.equal(material.question, "先看 Codex 为什么走 WebSocket");
  assert.ok(material.answer.includes("我分两部分回答"), material.answer);
  assert.ok(material.answer.includes("保持 WebSocket 长连接"), "the final answer part is included");
  assert.equal(material.answer.includes("上游也有 WebSocket"), false, "the next turn is not borrowed");
});

test("a tail read of a newer turn does not borrow its answer for the named turn", async () => {
  const entries = [
    { type: "user_message", text: "先看 Codex 为什么走 WebSocket", turnId: "t1" },
    { type: "tool_call", text: "TOOL-1", turnId: "t1" },
    { type: "user_message", text: "换一个话题", turnId: "t2" },
    { type: "assistant_message", text: "新话题的答复在这里。", turnId: "t2" },
  ];
  const paseo = { agents: { ref: () => ({ timeline: fakeTimeline(entries) }) } };
  const material = await readSessionNamingMaterial(paseo, "a1", { turnId: "t1" });
  assert.equal(material.question, "先看 Codex 为什么走 WebSocket");
  assert.equal(material.answer, null, "another turn's answer is not naming material");
});

test("session naming keeps the first question when the answer came on a later turn", async () => {
  const entries = [
    { type: "user_message", text: "先看 Codex 为什么走 WebSocket", turnId: "t1" },
    { type: "user_message", text: "那 CCHP 上游呢", turnId: "t2" },
    { type: "assistant_message", text: "CCHP 上游也有一条 WebSocket，失败时回退 HTTP。", turnId: "t2" },
  ];
  const paseo = { agents: { ref: () => ({ timeline: fakeTimeline(entries) }) } };
  const material = await readSessionNamingMaterial(paseo, "a1", { turnId: "t2" });
  assert.equal(material.question, "先看 Codex 为什么走 WebSocket");
  assert.equal(material.answer, "CCHP 上游也有一条 WebSocket，失败时回退 HTTP。");
  assert.equal(material.turnId, "t2");
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
