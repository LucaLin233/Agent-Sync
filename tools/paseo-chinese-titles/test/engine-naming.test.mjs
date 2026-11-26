import test from "node:test";
import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { settingsSchema } from "../shared/settings.ts";

// The engine stores its state under $PASEO_HOME/plugin-data; point HOME and
// PASEO_HOME at a private temp root so the test never touches real data.
const liveEngines = [];

async function withSandbox(run) {
  const root = await fs.mkdtemp(join(tmpdir(), "chinese-titles-engine-"));
  const previous = { HOME: process.env.HOME, PASEO_HOME: process.env.PASEO_HOME };
  process.env.HOME = root;
  process.env.PASEO_HOME = join(root, "paseo-home");
  try {
    return await run(root);
  } finally {
    while (liveEngines.length > 0) await liveEngines.pop().dispose();
    if (previous.HOME === undefined) delete process.env.HOME; else process.env.HOME = previous.HOME;
    if (previous.PASEO_HOME === undefined) delete process.env.PASEO_HOME; else process.env.PASEO_HOME = previous.PASEO_HOME;
    await fs.rm(root, { recursive: true, force: true });
  }
}

const FIRST_PROMPT = "先看 Codex 为什么走 WebSocket";

function makeTimeline(state) {
  const entries = [];
  for (const turn of state.turns) {
    entries.push({ type: "user_message", text: turn.question, turnId: turn.id });
    if (turn.answer !== null) entries.push({ type: "assistant_message", text: turn.answer, turnId: turn.id });
  }
  const rows = entries.map((item, index) => ({
    provider: "codex",
    item,
    turnId: item.turnId,
    timestamp: "2026-11-24T00:00:00.000Z",
    seqStart: index + 1,
    seqEnd: index + 1,
    sourceSeqRanges: [],
    collapsed: [],
  }));
  return {
    refetch: async (options = {}) => {
      const limit = options.limit ?? 50;
      const start = options.cursor?.seq ?? 0;
      const end = Math.min(rows.length, start + limit);
      return {
        direction: "after",
        projection: "projected",
        hasOlder: start > 0,
        hasNewer: end < rows.length,
        startCursor: { epoch: "e1", seq: start + 1 },
        endCursor: { epoch: "e1", seq: end },
        entries: rows.slice(start, end),
        reset: false,
        staleCursor: false,
        gap: false,
        error: null,
      };
    },
  };
}

function makePaseo(state) {
  const paseo = {
    config: { get: async () => ({ config: { providers: { cchp: { extends: "codex", label: "CCHP" } } } }) },
    providers: {
      snapshot: async () => ({ entries: [{
        provider: "cchp",
        status: "ready",
        enabled: true,
        models: [{ id: "m1", label: "M", isDefault: true }],
      }] }),
      listModels: async () => ({ models: [] }),
    },
    projects: { list: async () => ({ projects: [] }) },
    workspaces: {
      list: async () => ({ entries: [{ ...state.workspace }] }),
      ref: () => ({
        refresh: async () => ({ ...state.workspace }),
        setTitle: async (title) => {
          state.workspace.title = title;
          return { title };
        },
      }),
      create: async () => ({
        agents: {
          create: async () => ({
            run: async () => {
              const answer = state.modelAnswers.length > 0
                ? state.modelAnswers.shift()
                : "排查 Codex 连接方式";
              state.modelPrompts.push(answer);
              return { status: "idle", lastMessage: answer };
            },
            archive: async () => ({}),
          }),
        },
        archive: async () => ({}),
      }),
    },
    agents: {
      list: async () => ({
        entries: [{ agent: { ...state.agent } }],
        pageInfo: { hasMore: false },
      }),
      ref: () => ({
        refresh: async () => ({ agent: { ...state.agent } }),
        timeline: makeTimeline(state),
      }),
    },
  };
  return paseo;
}

async function harness(root, overrides = {}) {
  const { ChineseTitlesEngine } = await import("../server/engine.ts");
  const state = {
    workspace: {
      id: "w1",
      projectId: "p1",
      projectDisplayName: "Paseo",
      workspaceDirectory: "/synthetic/workspace",
      name: "w1",
      title: "已命名的工作区",
      background: false,
      metadata: {},
      archivingAt: null,
    },
    agent: {
      id: "a1",
      workspaceId: "w1",
      title: null,
      background: false,
      cwd: "/synthetic/workspace",
      labels: {},
      metadata: {},
      lastUserMessageAt: "2026-11-24T00:00:00.000Z",
      createdAt: "2026-11-24T00:00:00.000Z",
      updatedAt: "2026-11-24T00:00:00.000Z",
    },
    turns: [],
    modelAnswers: [],
    modelPrompts: [],
    renames: [],
    ...overrides,
  };
  if (state.agentTitle !== undefined) state.agent.title = state.agentTitle;
  // Seed the plugin's own state before the engine reads it in its constructor.
  if (state.legacyState) await writeState(root, state.legacyState);
  const settings = {
    read: async () => ({ status: "ready", values: settingsSchema.parse({ autoNameSessions: true }) }),
  };
  const engine = new ChineseTitlesEngine(settings, {
    renameAgent: async (_settings, agentId, title) => {
      state.renames.push({ agentId, title });
      state.agent.title = title;
      return { ok: true };
    },
  });
  const paseo = makePaseo(state);
  liveEngines.push(engine);
  return { engine, state, paseo };
}

/** Seeds the plugin's own persisted state for the synthetic daemon namespace. */
async function writeState(root, agentEntry) {
  const dir = join(root, "paseo-home", "plugin-data", "paseo-chinese-titles");
  await fs.mkdir(dir, { recursive: true, mode: 0o700 });
  await fs.writeFile(join(dir, "state.json"), JSON.stringify({
    version: 1,
    initialized: true,
    installedAt: "2026-11-20T00:00:00.000Z",
    projects: {},
    workspaces: { w1: { status: "done", at: "2026-11-20T00:00:00.000Z", title: "已命名的工作区" } },
    agents: { a1: agentEntry },
  }), { encoding: "utf8", mode: 0o600 });
}

/** Reads the plugin's own persisted state for the synthetic daemon namespace. */
async function agentState(root) {
  const file = join(join(root, "paseo-home", "plugin-data", "paseo-chinese-titles"), "state.json");
  const raw = await fs.readFile(file, "utf8").catch(() => null);
  if (!raw) return {};
  return JSON.parse(raw).agents?.a1 ?? {};
}

test("scenario B: the first failed title keeps the provisional one, the next turn retries, then it stops", async () => {
  await withSandbox(async (root) => {
    const { engine, state, paseo } = await harness(root);
    state.agent.title = FIRST_PROMPT;
    state.turns = [
      { id: "t1", question: FIRST_PROMPT, answer: "Codex 客户端与 daemon 之间保持了 WebSocket 长连接。" },
    ];
    // The first model run returns a non-Chinese answer: no usable title.
    state.modelAnswers = ["Fix login bug"];

    await engine.onTurnAfter("a1", "t1", paseo, true);
    assert.deepEqual(state.renames, [], "a failed title must not be written");
    assert.equal(state.agent.title, FIRST_PROMPT, "the provisional title stays live");
    let saved = await agentState(root);
    assert.equal(saved.status, "pending");
    assert.equal(saved.attempts, 1);
    assert.equal(saved.lastTurnId, "t1");
    assert.equal(saved.title, undefined, "a failed attempt never records a title");

    // The same completed turn redelivered must not spend the second attempt.
    await engine.onTurnAfter("a1", "t1", paseo, true);
    assert.equal(state.modelPrompts.length, 1, "no extra model call for a duplicate event");
    assert.equal((await agentState(root)).attempts, 1);

    // A later completed turn retries once and succeeds.
    state.turns.push({ id: "t2", question: "那 CCHP 上游呢", answer: "CCHP 上游也有独立的 WebSocket，失败时回退 HTTP。" });
    state.modelAnswers = ["排查 Codex 与 CCHP 连接方式"];
    await engine.onTurnAfter("a1", "t2", paseo, true);
    assert.deepEqual(state.renames, [{ agentId: "a1", title: "排查 Codex 与 CCHP 连接方式" }]);
    saved = await agentState(root);
    assert.equal(saved.status, "done");
    assert.equal(saved.attempts, 2);

    // After success, another completed turn never renames again.
    state.turns.push({ id: "t3", question: "最后停用 CCHP", answer: "已停用 CCHP 和 GDR。" });
    state.modelAnswers = ["错误覆盖标题"];
    await engine.onTurnAfter("a1", "t3", paseo, true);
    assert.equal(state.renames.length, 1);
    assert.equal(state.agent.title, "排查 Codex 与 CCHP 连接方式");
  });
});

test("a first page that is already a reset tail is never taken as the session opening", async () => {
  await withSandbox(async (root) => {
    const { engine, state, paseo } = await harness(root);
    state.agent.title = FIRST_PROMPT;
    state.turns = [{ id: "t1", question: FIRST_PROMPT, answer: "Codex 客户端与 daemon 之间保持了 WebSocket 长连接。" }];
    state.modelAnswers = ["排查 Codex 连接方式"];

    // Control: an ordinary head page does yield the real first question.
    const first = await engine.readFirstPrompt(paseo, "a1");
    assert.equal(first?.text, FIRST_PROMPT);

    // Paseo 0.17.4 serves a stale-cursor reset as a tail page on the very first
    // request too. Its first user message is mid-session, not the opening, so it
    // must not be reported as the session's first task at all.
    const originalRef = paseo.agents.ref;
    paseo.agents.ref = (id) => {
      const handle = originalRef(id);
      return {
        ...handle,
        timeline: {
          refetch: async (options = {}) => ({
            ...(await handle.timeline.refetch(options)),
            reset: true,
            staleCursor: true,
            gap: false,
            hasNewer: false,
          }),
        },
      };
    };
    assert.equal(await engine.readFirstPrompt(paseo, "a1"), null, "a first-page reset proves nothing about the opening");

    // And the whole turn then spends no naming attempt on that mid-session text.
    await engine.onTurnAfter("a1", "t1", paseo, true);
    assert.equal(state.modelPrompts.length, 0);
    assert.deepEqual(state.renames, []);
  });
});

test("a failed or tool-only turn spends nothing, and two failures exhaust the retry", async () => {
  await withSandbox(async (root) => {
    const { engine, state, paseo } = await harness(root);
    state.agent.title = FIRST_PROMPT;
    state.turns = [{ id: "t1", question: FIRST_PROMPT, answer: null }];
    state.modelAnswers = ["不该用到"];
    await engine.onTurnAfter("a1", "t1", paseo, false);
    assert.equal((await agentState(root)).attempts, undefined);
    assert.deepEqual(state.renames, []);

    state.turns[0].answer = "ok";
    await engine.onTurnAfter("a1", "t1", paseo, true);
    assert.deepEqual(state.renames, [], "a tool-only answer is not naming material");

    state.turns[0].answer = "Codex 走 WebSocket 是因为长连接要推送事件。";
    state.modelAnswers = ["Fix login bug", "still english"];
    await engine.onTurnAfter("a1", "t1", paseo, true);
    assert.equal((await agentState(root)).attempts, 1);
    state.turns.push({ id: "t2", question: "继续", answer: "CCHP 上游也走 WebSocket。" });
    await engine.onTurnAfter("a1", "t2", paseo, true);
    const spent = await agentState(root);
    assert.equal(spent.attempts, 2);
    assert.equal(spent.status, "skipped");
    state.turns.push({ id: "t3", question: "再试", answer: "回退到了 HTTP。" });
    await engine.onTurnAfter("a1", "t3", paseo, true);
    assert.equal((await agentState(root)).attempts, 2, "exhausted sessions stop");
  });
});

test("a manual rename during generation wins and is never overwritten", async () => {
  await withSandbox(async (root) => {
    const { engine, state, paseo } = await harness(root);
    state.agent.title = FIRST_PROMPT;
    state.turns = [{ id: "t1", question: FIRST_PROMPT, answer: "Codex 走 WebSocket 是为了推送事件。" }];
    const ref = paseo.agents.ref;
    let refreshed = 0;
    paseo.agents.ref = () => {
      const handle = ref();
      return {
        ...handle,
        refresh: async () => {
          refreshed += 1;
          // The user renames the session while the model is running.
          if (refreshed >= 2) state.agent.title = "我自己起的中文标题";
          return { agent: { ...state.agent } };
        },
      };
    };
    state.modelAnswers = ["模型想写的标题"];
    await engine.onTurnAfter("a1", "t1", paseo, true);
    assert.deepEqual(state.renames, [], "the manual title wins");
    assert.equal(state.agent.title, "我自己起的中文标题");
  });
});

test("a legacy done+model_failed title is repaired once when it is still the live title", async () => {
  await withSandbox(async (root) => {
    // The old code truncated the first sentence and stored it as `done`.
    const { engine, state, paseo } = await harness(root, {
      legacyState: { status: "done", title: "先看 Codex 为什么走 WebSoc", error: "model_failed", at: "2026-11-20T00:00:00.000Z" },
      agentTitle: "先看 Codex 为什么走 WebSoc",
    });
    state.turns = [{ id: "t1", question: FIRST_PROMPT, answer: "Codex 客户端与 daemon 之间保持 WebSocket 长连接。" }];
    state.modelAnswers = ["排查 Codex 长连接原因"];
    await engine.onTurnAfter("a1", "t1", paseo, true);
    assert.deepEqual(state.renames, [{ agentId: "a1", title: "排查 Codex 长连接原因" }]);
    const saved = await agentState(root);
    assert.equal(saved.status, "done");
    assert.equal(saved.repairUsed, true);
    // The repair is spent once; a later completed turn changes nothing.
    state.turns.push({ id: "t2", question: "继续", answer: "CCHP 上游也走 WebSocket。" });
    state.modelAnswers = ["不该覆盖"];
    await engine.onTurnAfter("a1", "t2", paseo, true);
    assert.equal(state.renames.length, 1);
  });
});

test("a canceled turn with partial text never spends the legacy repair", async () => {
  await withSandbox(async (root) => {
    const { engine, state, paseo } = await harness(root, {
      legacyState: { status: "done", title: "先看 Codex 为什么走 WebSoc", error: "model_failed", at: "2026-11-20T00:00:00.000Z" },
      agentTitle: "先看 Codex 为什么走 WebSoc",
    });
    // The provider streamed an assistant fragment before the turn was canceled.
    state.turns = [{ id: "t1", question: FIRST_PROMPT, answer: "我先看一下 Codex 的连接方式，接着" }];
    state.modelAnswers = ["不该调用模型"];
    await engine.onTurnAfter("a1", "t1", paseo, false);
    assert.deepEqual(state.renames, [], "a canceled turn must not rename");
    assert.equal(state.modelPrompts.length, 0, "and must not call the model");
    const untouched = await agentState(root);
    assert.equal(untouched.repairUsed, undefined, "the single repair is still available");
    assert.equal(untouched.status, "done");

    // The next finished turn spends it.
    state.turns.push({ id: "t2", question: "继续", answer: "Codex 与 daemon 之间保持 WebSocket 长连接。" });
    state.modelAnswers = ["排查 Codex 长连接原因"];
    await engine.onTurnAfter("a1", "t2", paseo, true);
    assert.deepEqual(state.renames, [{ agentId: "a1", title: "排查 Codex 长连接原因" }]);
    assert.equal((await agentState(root)).repairUsed, true);
  });
});

test("the write is re-checked after generation: a gone or changed agent is never renamed", async () => {
  await withSandbox(async (root) => {
    const cases = [
      { name: "the agent disappeared", mutate: () => undefined },
      { name: "the agent was archived", mutate: (agent) => ({ ...agent, archivedAt: "2026-11-24T00:00:00.000Z" }) },
      { name: "the agent moved workspace", mutate: (agent) => ({ ...agent, workspaceId: "w2" }) },
      { name: "the user renamed it", mutate: (agent) => ({ ...agent, title: "用户手动标题" }) },
    ];
    for (const entry of cases) {
      const { engine, state, paseo } = await harness(root);
      state.agent.title = FIRST_PROMPT;
      state.turns = [{ id: "t1", question: FIRST_PROMPT, answer: "Codex 与 daemon 之间保持 WebSocket 长连接。" }];
      state.modelAnswers = ["排查 Codex 连接方式"];
      // The first refresh runs before the model; the one after it is the
      // write-preceding re-read that must notice the change.
      let refreshes = 0;
      const originalRef = paseo.agents.ref;
      paseo.agents.ref = (id) => {
        const handle = originalRef(id);
        return {
          ...handle,
          refresh: async () => {
            refreshes += 1;
            if (refreshes <= 1) return handle.refresh();
            const next = entry.mutate(state.agent);
            return next === undefined ? {} : { agent: next };
          },
        };
      };
      await engine.onTurnAfter("a1", "t1", paseo, true);
      assert.deepEqual(state.renames, [], `${entry.name}: no CLI rename`);
      const saved = await agentState(root);
      assert.equal(saved.status, "skipped", `${entry.name}: recorded as skipped`);
    }
  });
});

test("a refresh that eats the naming budget records timeout and writes nothing", async () => {
  await withSandbox(async (root) => {
    const { engine, state, paseo } = await harness(root);
    state.agent.title = FIRST_PROMPT;
    state.turns = [{ id: "t1", question: FIRST_PROMPT, answer: "Codex 与 daemon 之间保持 WebSocket 长连接。" }];
    state.modelAnswers = ["排查 Codex 连接方式"];

    const realNow = Date.now;
    let refreshed = 0;
    const originalRef = paseo.agents.ref;
    paseo.agents.ref = (id) => {
      const handle = originalRef(id);
      return {
        ...handle,
        refresh: async () => {
          refreshed += 1;
          // The model already answered; this is the slow pre-write re-read. Burn
          // most of the 20 s naming budget so only a rename-sized gap is left.
          if (refreshed > 1) Date.now = () => realNow() + 17_500;
          return handle.refresh();
        },
      };
    };
    try {
      await engine.onTurnAfter("a1", "t1", paseo, true);
    } finally {
      Date.now = realNow;
    }
    assert.deepEqual(state.renames, [], "an expired budget must not start the CLI rename");
    assert.equal(state.agent.title, FIRST_PROMPT, "the provisional title stays");
    const saved = await agentState(root);
    assert.equal(saved.error, "timeout");
    assert.equal(saved.attempts, 1);
    assert.equal(saved.status, "pending", "one attempt is spent, the later turn may still retry");
  });
});

test("a legacy entry whose title was changed by hand is left alone", async () => {
  await withSandbox(async (root) => {
    const { engine, state, paseo } = await harness(root, {
      legacyState: { status: "done", title: "先看 Codex 为什么走 WebSoc", error: "model_failed", at: "2026-11-20T00:00:00.000Z" },
      agentTitle: "用户手动改过的标题",
    });
    state.turns = [{ id: "t1", question: FIRST_PROMPT, answer: "Codex 走 WebSocket 以推送事件。" }];
    state.modelAnswers = ["模型想写的标题"];
    await engine.onTurnAfter("a1", "t1", paseo, true);
    assert.deepEqual(state.renames, []);
    assert.equal(state.agent.title, "用户手动改过的标题");
  });
});

test("an explicit title and a legacy baseline entry are never named", async () => {
  await withSandbox(async (root) => {
    const { engine, state, paseo } = await harness(root);
    state.agent.title = "用户明确起的名字";
    state.turns = [{ id: "t1", question: FIRST_PROMPT, answer: "Codex 走 WebSocket。" }];
    state.modelAnswers = ["模型标题"];
    await engine.onTurnAfter("a1", "t1", paseo, true);
    assert.deepEqual(state.renames, []);
    assert.equal((await agentState(root)).status, "skipped");
  });
});
