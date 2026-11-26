import test from "node:test";
import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pickFirstTaskOwner, planWorkspaceRepair, planWorkspaceRetry } from "../shared/workspace-repair.ts";
import { settingsSchema } from "../shared/settings.ts";

const FALLBACK = "整理一份产品需求清单并排出实施顺序";
const SESSION_TITLE = "梳理需求清单并规划实施步骤";
const FIRST_TASK = "整理一份产品需求清单，按优先级排出实施顺序";

function fallbackState(overrides = {}) {
  return { status: "done", at: "2026-01-02T03:04:05.678Z", title: FALLBACK, error: "model_failed", ...overrides };
}

function input(overrides = {}) {
  return {
    workspaceState: fallbackState(),
    liveTitle: FALLBACK,
    firstTask: FIRST_TASK,
    sessionTitle: SESSION_TITLE,
    sessionState: { status: "done", at: "2026-01-02T03:04:23.138Z", title: SESSION_TITLE },
    firstTaskOwner: true,
    idle: true,
    maxChars: 28,
    ...overrides,
  };
}

test("a recorded fallback adopts its verified session title unchanged", () => {
  // The workspace kept the plugin's fallback while its only session already
  // had a verified Chinese title.
  const decision = planWorkspaceRepair(input({
    workspaceState: {
      status: "done",
      at: "2026-01-02T03:04:05.678Z",
      title: "整理一份产品需求清单并排出实施顺序",
      previousTitle: "整理一份产品需求清单并排出实施顺序",
      error: "model_failed",
    },
    liveTitle: "整理一份产品需求清单并排出实施顺序",
    firstTask: "整理一份产品需求清单并排出实施顺序",
    sessionTitle: "梳理需求清单并规划实施步骤",
    sessionState: {
      status: "done",
      at: "2026-01-02T03:04:23.138Z",
      title: "梳理需求清单并规划实施步骤",
      attempts: 1,
      lastTurnId: null,
    },
    firstTaskOwner: true,
    idle: true,
    maxChars: 28,
  }));
  assert.deepEqual(decision, { kind: "repair", title: "梳理需求清单并规划实施步骤" });
  // The fallback was recorded first and the session title arrived 17.460 s
  // later: the workspace had already been closed as `done` with a failure
  // code, so only this repair path can still use it.
  assert.equal(Date.parse("2026-01-02T03:04:23.138Z") - Date.parse("2026-01-02T03:04:05.678Z"), 17_460);
});

test("a recorded fallback workspace adopts its verified first-task session title", () => {
  assert.deepEqual(planWorkspaceRepair(input()), { kind: "repair", title: SESSION_TITLE });
});

test("a workspace with no recorded fallback is never touched, even when its title is provisional", () => {
  assert.deepEqual(
    planWorkspaceRepair(input({ workspaceState: { status: "pending", at: "2026-01-02T03:04:02.000Z" }, liveTitle: FIRST_TASK })),
    { kind: "blocked", reason: "no_placeholder" },
  );
  assert.deepEqual(
    planWorkspaceRepair(input({ workspaceState: { status: "error", at: "2026-01-02T03:04:02.000Z", error: "internal_failed" } })),
    { kind: "blocked", reason: "no_placeholder" },
  );
  assert.deepEqual(
    planWorkspaceRepair(input({ workspaceState: { status: "legacy", at: "2026-01-02T03:04:02.000Z" } })),
    { kind: "blocked", reason: "no_placeholder" },
  );
});

test("a provider outage fallback is repairable like any other fallback", () => {
  assert.deepEqual(
    planWorkspaceRepair(input({ workspaceState: fallbackState({ error: "provider_unavailable" }) })),
    { kind: "repair", title: SESSION_TITLE },
  );
});

test("a manual workspace rename is never treated as a placeholder", () => {
  assert.deepEqual(
    planWorkspaceRepair(input({ liveTitle: "我手动起的名字" })),
    { kind: "blocked", reason: "title_changed" },
  );
  assert.deepEqual(
    planWorkspaceRepair(input({ workspaceState: fallbackState({ title: "旧的手动标题" }) })),
    { kind: "blocked", reason: "title_changed" },
  );
});

test("a merely non-empty session never donates a title", () => {
  // Unverified session: never generated or verified by this plugin.
  assert.deepEqual(
    planWorkspaceRepair(input({ sessionState: undefined })),
    { kind: "blocked", reason: "session_not_verified" },
  );
  // A recorded failure is not a title either.
  assert.deepEqual(
    planWorkspaceRepair(input({ sessionState: { status: "done", title: SESSION_TITLE, error: "model_failed" } })),
    { kind: "blocked", reason: "session_not_verified" },
  );
  // The plugin's record no longer matches the live title (renamed by hand).
  assert.deepEqual(
    planWorkspaceRepair(input({ sessionTitle: "手工改过的会话名" })),
    { kind: "blocked", reason: "session_not_verified" },
  );
});

test("a session that does not own the first task cannot rename the workspace", () => {
  assert.deepEqual(
    planWorkspaceRepair(input({ firstTaskOwner: false })),
    { kind: "blocked", reason: "not_first_task" },
  );
});

test("Paseo's provisional text is never written as a repair title", () => {
  assert.deepEqual(
    planWorkspaceRepair(input({
      sessionTitle: FIRST_TASK,
      sessionState: { status: "done", title: FIRST_TASK },
    })),
    { kind: "blocked", reason: "session_not_verified" },
  );
});

test("a session title identical to the placeholder is not recorded as a repair", () => {
  assert.deepEqual(
    planWorkspaceRepair(input({ sessionTitle: FALLBACK, sessionState: { status: "done", title: FALLBACK } })),
    { kind: "blocked", reason: "session_not_verified" },
  );
  // The seed title this workspace had before the fallback is a placeholder too:
  // writing it back would only re-arm Paseo's provisional handling.
  assert.deepEqual(
    planWorkspaceRepair(input({
      workspaceState: fallbackState({ previousTitle: "整理一份产品需求清单并排出实施顺序" }),
      sessionTitle: "整理一份产品需求清单并排出实施顺序",
      sessionState: { status: "done", title: "整理一份产品需求清单并排出实施顺序" },
    })),
    { kind: "blocked", reason: "session_not_verified" },
  );
});

test("a title longer than the configured limit is left for the manual action", () => {
  const long = "梳理全部需求条目并规划后续实施顺序与验收证据";
  assert.ok(Array.from(long).length > 12);
  assert.deepEqual(
    planWorkspaceRepair(input({ sessionTitle: long, sessionState: { status: "done", title: long }, maxChars: 12 })),
    { kind: "blocked", reason: "session_not_verified" },
  );
});

test("the model retry runs once, and only while the recorded fallback is still live", () => {
  assert.deepEqual(planWorkspaceRetry({ workspaceState: fallbackState(), liveTitle: FALLBACK }), { kind: "retry" });
  assert.deepEqual(
    planWorkspaceRetry({ workspaceState: fallbackState({ retryUsed: true }), liveTitle: FALLBACK }),
    { kind: "blocked", reason: "retry_used" },
  );
  assert.deepEqual(
    planWorkspaceRetry({ workspaceState: fallbackState(), liveTitle: "手动改过的名字" }),
    { kind: "blocked", reason: "title_changed" },
  );
  assert.deepEqual(
    planWorkspaceRetry({ workspaceState: { status: "done", title: FALLBACK }, liveTitle: FALLBACK }),
    { kind: "blocked", reason: "no_placeholder" },
  );
});

test("a spent repair and an in-flight naming step stay blocked", () => {
  assert.deepEqual(
    planWorkspaceRepair(input({ workspaceState: fallbackState({ repairUsed: true }) })),
    { kind: "blocked", reason: "repair_used" },
  );
  assert.deepEqual(
    planWorkspaceRepair(input({ idle: false })),
    { kind: "blocked", reason: "in_flight" },
  );
  assert.deepEqual(
    planWorkspaceRepair(input({ workspaceState: { status: "done", title: FALLBACK } })),
    { kind: "blocked", reason: "no_placeholder" },
  );
});

test("first-task ownership is decided from metadata, not message text", () => {
  const fallbackAt = "2026-01-02T03:04:05.678Z";
  // The reported pair: one session existed before the fallback was recorded.
  assert.deepEqual(
    pickFirstTaskOwner([
      { id: "a1", createdAt: "2026-01-02T03:04:02.000Z", lastUserMessageAt: "2026-01-02T03:04:02.500Z" },
    ], fallbackAt),
    { kind: "owner", id: "a1" },
  );
  // A session created after the fallback cannot have owned the first task.
  assert.deepEqual(
    pickFirstTaskOwner([
      { id: "a1", createdAt: "2026-01-02T03:04:02.000Z", lastUserMessageAt: "2026-01-02T03:04:02.500Z" },
      { id: "a2", createdAt: "2026-01-02T05:00:00.000Z", lastUserMessageAt: "2026-01-02T05:00:00.000Z" },
    ], fallbackAt),
    { kind: "owner", id: "a1" },
  );
  // An earlier session that never received a task does not block the later
  // session that did: ownership follows the only session that sent a message.
  assert.deepEqual(
    pickFirstTaskOwner([
      { id: "a1", createdAt: "2026-01-02T02:00:00.000Z", lastUserMessageAt: null },
      { id: "a2", createdAt: "2026-01-02T03:04:02.000Z", lastUserMessageAt: "2026-01-02T03:04:02.500Z" },
    ], fallbackAt),
    { kind: "owner", id: "a2" },
  );
  // Two sessions that both predate it cannot be separated by metadata.
  assert.deepEqual(
    pickFirstTaskOwner([
      { id: "a1", createdAt: "2026-01-02T03:04:02.000Z", lastUserMessageAt: "2026-01-02T03:04:02.500Z" },
      { id: "a2", createdAt: "2026-01-02T03:04:03.000Z", lastUserMessageAt: "2026-01-02T03:04:03.500Z" },
    ], fallbackAt),
    { kind: "unknown" },
  );
  // A session that never received a user message is not a task owner, and an
  // unreadable timestamp never turns into a guessed owner.
  assert.deepEqual(pickFirstTaskOwner([{ id: "a1", createdAt: "2026-01-02T03:04:02.000Z" }], fallbackAt), { kind: "unknown" });
  assert.deepEqual(
    pickFirstTaskOwner([{ id: "a1", createdAt: "not-a-time", lastUserMessageAt: "2026-01-02T03:04:02.500Z" }], fallbackAt),
    { kind: "unknown" },
  );
  assert.deepEqual(pickFirstTaskOwner([], fallbackAt), { kind: "unknown" });
  assert.deepEqual(
    pickFirstTaskOwner([{ id: "a1", createdAt: "2026-01-02T03:04:02.000Z", lastUserMessageAt: "2026-01-02T03:04:02.500Z" }], null),
    { kind: "unknown" },
  );
});

/** Seeds the plugin's persisted state for the sandbox's synthetic daemon. */
async function writeState(root, workspaces, agents) {
  const dir = join(root, "paseo-home", "plugin-data", "paseo-chinese-titles");
  await fs.mkdir(dir, { recursive: true, mode: 0o700 });
  await fs.writeFile(join(dir, "state.json"), JSON.stringify({
    version: 1, initialized: true, installedAt: "2026-01-01T00:00:00.000Z", projects: {}, workspaces, agents,
  }), { encoding: "utf8", mode: 0o600 });
}

function makeAgent(id, title, lastUserMessageAt) {
  return {
    id,
    workspaceId: "w1",
    title,
    background: false,
    cwd: "/synthetic/workspace",
    labels: {},
    metadata: {},
    archivedAt: null,
    lastUserMessageAt,
    createdAt: lastUserMessageAt,
    updatedAt: lastUserMessageAt,
  };
}

function makePaseo(state) {
  const timeline = {
    refetch: async () => {
      state.timelineReads = (state.timelineReads ?? 0) + 1;
      return {
      direction: "after",
      projection: "projected",
      hasOlder: false,
      hasNewer: false,
      startCursor: { epoch: "e1", seq: 1 },
      endCursor: { epoch: "e1", seq: 2 },
      entries: [
        { item: { type: "user_message", text: FIRST_TASK }, turnId: "t1", timestamp: "2026-01-02T03:04:02.000Z" },
        { item: { type: "assistant_message", text: "已经核对" }, turnId: "t1", timestamp: "2026-01-02T03:04:12.000Z" },
      ],
      error: null,
      };
    },
  };
  return {
    config: { get: async () => ({ config: { providers: {} } }) },
    providers: { snapshot: async () => ({ entries: [] }), listModels: async () => ({ models: [] }) },
    projects: { list: async () => ({ projects: [] }) },
    workspaces: {
      list: async () => ({ entries: [{ ...state.workspace }] }),
      ref: () => ({
        refresh: async () => {
          state.workspaceReads = (state.workspaceReads ?? 0) + 1;
          // The repair reads the workspace first and then still has async
          // ownership work to do; a manual rename landing in that window must
          // not be overwritten.
          if (state.workspaceReads === 1) state.renameAfterFirstRead = true;
          return { ...state.workspace };
        },
        setTitle: async (title) => {
          state.writes.push(title);
          state.workspace.title = title;
          return { title };
        },
      }),
    },
    agents: {
      list: async () => {
        state.agentListCalls = (state.agentListCalls ?? 0) + 1;
        if (state.renameAfterFirstRead) {
          state.renameAfterFirstRead = false;
          state.renameInOwnershipWindow?.();
        }
        return { entries: state.agents.map((agent) => ({ agent: { ...agent } })), pageInfo: { hasMore: false } };
      },
      ref: (id) => ({
        refresh: async () => {
          const agent = state.agents.find((entry) => entry.id === id);
          return agent ? { agent: { ...agent } } : null;
        },
        timeline,
      }),
    },
  };
}

function makeState(agents) {
  return {
    workspace: {
      id: "w1",
      projectId: "p1",
      projectDisplayName: "Paseo",
      workspaceDirectory: "/synthetic/workspace",
      name: "Paseo",
      title: FALLBACK,
      background: false,
      metadata: {},
      archivingAt: null,
    },
    agents,
    writes: [],
  };
}

async function withSandbox(run) {
  const root = await fs.mkdtemp(join(tmpdir(), "chinese-titles-repair-"));
  const previous = { HOME: process.env.HOME, PASEO_HOME: process.env.PASEO_HOME };
  process.env.HOME = root;
  process.env.PASEO_HOME = join(root, "paseo-home");
  const engines = [];
  try {
    await run(root, engines);
  } finally {
    while (engines.length > 0) await engines.pop().dispose();
    if (previous.HOME === undefined) delete process.env.HOME; else process.env.HOME = previous.HOME;
    if (previous.PASEO_HOME === undefined) delete process.env.PASEO_HOME; else process.env.PASEO_HOME = previous.PASEO_HOME;
    await fs.rm(root, { recursive: true, force: true });
  }
}

async function runReconcile(root, engines, state, workspaces, agents) {
  const { ChineseTitlesEngine } = await import("../server/engine.ts");
  await writeState(root, workspaces, agents);
  const settings = {
    read: async () => ({
      status: "ready",
      revision: "r1",
      values: settingsSchema.parse({ autoNameProjects: false, autoNameWorkspaces: true, autoNameSessions: false }),
    }),
  };
  const engine = new ChineseTitlesEngine(settings, { renameAgent: async () => ({ ok: false, failure: "unused" }) });
  engines.push(engine);
  await engine.usePaseo(makePaseo(state));
  return engine.reconcile(makePaseo(state));
}

test("reconcile repairs a stuck fallback workspace from its own first-task session", async () => {
  await withSandbox(async (root, engines) => {
    const state = makeState([makeAgent("a1", SESSION_TITLE, "2026-01-02T03:04:02.000Z")]);
    await runReconcile(
      root,
      engines,
      state,
      { w1: fallbackState() },
      { a1: { status: "done", at: "2026-01-02T03:04:23.138Z", title: SESSION_TITLE, attempts: 1 } },
    );
    assert.deepEqual(state.writes, [SESSION_TITLE]);
    assert.equal(state.workspace.title, SESSION_TITLE);
    // The repair decides ownership from metadata and adopts the recorded
    // session title, so it never reads that session's message text.
    assert.equal(state.timelineReads ?? 0, 0);
  });
});

test("reconcile leaves the workspace alone when a second session has the only title", async () => {
  await withSandbox(async (root, engines) => {
    // a1 owns the first task but was never verified; a2 has a title from a
    // later conversation and must not rename the workspace.
    const state = makeState([
      makeAgent("a1", "排一份产品需求清单，按优先级处理", "2026-01-02T03:04:02.000Z"),
      makeAgent("a2", "另一个会话的合成标题", "2026-01-02T05:00:00.000Z"),
    ]);
    await runReconcile(
      root,
      engines,
      state,
      { w1: fallbackState() },
      {
        a1: { status: "skipped", at: "2026-01-02T03:04:12.000Z" },
        a2: { status: "done", at: "2026-01-02T05:00:05.000Z", title: "另一个会话的合成标题", attempts: 1 },
      },
    );
    assert.deepEqual(state.writes, []);
    assert.equal(state.workspace.title, FALLBACK);
  });
});

test("sub-agents never donate a title", async () => {
  await withSandbox(async (root, engines) => {
    // One user session created just before the fallback, plus sub-agent
    // children (one already archived) that also carry titles. Only the user
    // session may donate. The first child is dated before the fallback so the
    // timestamp guard alone cannot exclude it: the parent-agent label must.
    const state = makeState([
      { ...makeAgent("s1", "子会话的合成标题", "2026-01-02T03:04:03.000Z"), labels: { "paseo.parent-agent-id": "a1" } },
      makeAgent("a1", SESSION_TITLE, "2026-01-02T03:04:02.000Z"),
      { ...makeAgent("s3", "后续分析 · 梳理需求清单并规划实施步骤", "2026-01-02T03:20:00.000Z"), archivedAt: "2026-01-02T03:21:00.000Z", labels: { "paseo.parent-agent-id": "a1" } },
      { ...makeAgent("s4", "写入已确认的需求反馈", null), labels: { "paseo.parent-agent-id": "a1" } },
      { ...makeAgent("s5", "落实需求反馈候选", null), labels: { "paseo.parent-agent-id": "a1" } },
      { ...makeAgent("s6", "拟定需求反馈入口补丁", null), labels: { "paseo.parent-agent-id": "a1" } },
      { ...makeAgent("s7", "拟定需求清单的最小措辞", null), labels: { "paseo.parent-agent-id": "a1" } },
    ]);
    await runReconcile(
      root,
      engines,
      state,
      { w1: fallbackState() },
      {
        "s1": { status: "done", at: "2026-01-02T03:04:12.000Z", title: "子会话的合成标题", attempts: 1 },
        "a1": { status: "done", at: "2026-01-02T03:04:23.138Z", title: SESSION_TITLE, attempts: 1 },
        "s3": { status: "done", at: "2026-01-02T03:20:30.000Z", title: "后续分析 · 梳理需求清单并规划实施步骤", attempts: 1 },
      },
    );
    assert.deepEqual(state.writes, [SESSION_TITLE]);
    assert.equal(state.timelineReads ?? 0, 0);
  });
});

test("a manual workspace rename during the ownership lookup is never overwritten", async () => {
  await withSandbox(async (root, engines) => {
    const state = makeState([makeAgent("a1", SESSION_TITLE, "2026-01-02T03:04:02.000Z")]);
    // The user renames the workspace after the repair confirmed the fallback
    // and while it is still looking up the first-task owner.
    state.renameInOwnershipWindow = () => { state.workspace.title = "我手动起的名字"; };
    await runReconcile(
      root,
      engines,
      state,
      { w1: fallbackState() },
      { a1: { status: "done", at: "2026-01-02T03:04:23.138Z", title: SESSION_TITLE, attempts: 1 } },
    );
    assert.deepEqual(state.writes, []);
    assert.equal(state.workspace.title, "我手动起的名字");
  });
});

test("a manual session rename during the ownership lookup is never overwritten", async () => {
  await withSandbox(async (root, engines) => {
    const state = makeState([makeAgent("a1", SESSION_TITLE, "2026-01-02T03:04:02.000Z")]);
    // The user renames the donating session itself inside the same window, so
    // the title the repair wanted to adopt is no longer live.
    state.renameInOwnershipWindow = () => { state.agents[0].title = "手动改过的会话名"; };
    await runReconcile(
      root,
      engines,
      state,
      { w1: fallbackState() },
      { a1: { status: "done", at: "2026-01-02T03:04:23.138Z", title: SESSION_TITLE, attempts: 1 } },
    );
    assert.deepEqual(state.writes, []);
    assert.equal(state.workspace.title, FALLBACK);
  });
});

test("metadataless ambiguity keeps the placeholder instead of guessing the owner", async () => {
  await withSandbox(async (root, engines) => {
    // Both sessions predate the recorded fallback, so metadata cannot say which
    // one owned the first task; the verified title of either must not be used.
    const state = makeState([
      makeAgent("a1", SESSION_TITLE, "2026-01-02T03:04:02.000Z"),
      makeAgent("a2", "另一个会话的合成标题", "2026-01-02T03:04:03.000Z"),
    ]);
    await runReconcile(
      root,
      engines,
      state,
      { w1: fallbackState() },
      {
        a1: { status: "done", at: "2026-01-02T03:04:23.138Z", title: SESSION_TITLE, attempts: 1 },
        a2: { status: "done", at: "2026-01-02T03:04:24.000Z", title: "另一个会话的合成标题", attempts: 1 },
      },
    );
    assert.deepEqual(state.writes, []);
    assert.equal(state.workspace.title, FALLBACK);
    assert.equal(state.timelineReads ?? 0, 0);
  });
});

test("reconcile never overwrites a workspace the user renamed", async () => {
  await withSandbox(async (root, engines) => {
    const state = makeState([makeAgent("a1", SESSION_TITLE, "2026-01-02T03:04:02.000Z")]);
    state.workspace.title = "我手动起的名字";
    await runReconcile(
      root,
      engines,
      state,
      { w1: fallbackState() },
      { a1: { status: "done", at: "2026-01-02T03:04:23.138Z", title: SESSION_TITLE, attempts: 1 } },
    );
    assert.deepEqual(state.writes, []);
    assert.equal(state.workspace.title, "我手动起的名字");
  });
});

test("a session named on a later turn repairs its own stuck workspace in the same hook", async () => {
  await withSandbox(async (root, engines) => {
    const state = makeState([makeAgent("a1", FIRST_TASK, "2026-01-02T03:04:02.000Z")]);
    // The first turn already ran and its workspace model call failed.
    const paseo = makePaseo(state);
    const withModel = {
      ...paseo,
      config: { get: async () => ({ config: { providers: { cchp: { extends: "codex", label: "CCHP" } } } }) },
      providers: {
        snapshot: async () => ({
          entries: [{ provider: "cchp", status: "ready", enabled: true, models: [{ id: "m1", label: "M", isDefault: true }] }],
        }),
        listModels: async () => ({ models: [] }),
      },
      workspaces: {
        ...paseo.workspaces,
        create: async () => ({
          agents: {
            create: async () => ({
              run: async () => ({ status: "idle", lastMessage: SESSION_TITLE }),
              archive: async () => ({}),
            }),
          },
          archive: async () => ({}),
        }),
      },
    };
    const { ChineseTitlesEngine } = await import("../server/engine.ts");
    await writeState(
      root,
      { w1: fallbackState() },
      { a1: { status: "pending", at: "2026-01-02T03:04:02.000Z", attempts: 1, lastTurnId: null, workspaceId: "w1" } },
    );
    const settings = {
      read: async () => ({
        status: "ready",
        revision: "r1",
        values: settingsSchema.parse({ autoNameProjects: false, autoNameWorkspaces: true, autoNameSessions: true }),
      }),
    };
    const engine = new ChineseTitlesEngine(settings, {
      renameAgent: async (_values, agentId, title) => {
        const agent = state.agents.find((entry) => entry.id === agentId);
        if (!agent) return { ok: false, failure: "missing" };
        agent.title = title;
        return { ok: true };
      },
    });
    engines.push(engine);
    await engine.usePaseo(paseo);
    await engine.onTurnAfter("a1", "t1", withModel, true);
    assert.deepEqual(state.writes, [SESSION_TITLE]);
    assert.equal(state.workspace.title, SESSION_TITLE);
  });
});

test("a later session's turn never renames the workspace another session owns", async () => {
  await withSandbox(async (root, engines) => {
    // a1 opened the workspace but was never verified; a2 arrived later and has
    // a verified title of its own.
    const state = makeState([
      makeAgent("a1", "排一份产品需求清单，按优先级处理", "2026-01-02T03:04:02.000Z"),
      makeAgent("a2", "另一个会话的合成标题", "2026-01-02T05:00:00.000Z"),
    ]);
    const { ChineseTitlesEngine } = await import("../server/engine.ts");
    await writeState(
      root,
      { w1: fallbackState() },
      {
        a1: { status: "skipped", at: "2026-01-02T03:04:12.000Z", workspaceId: "w1" },
        a2: { status: "done", at: "2026-01-02T05:00:05.000Z", title: "另一个会话的合成标题", attempts: 1, workspaceId: "w1" },
      },
    );
    const settings = {
      read: async () => ({
        status: "ready",
        revision: "r1",
        values: settingsSchema.parse({ autoNameProjects: false, autoNameWorkspaces: true, autoNameSessions: false }),
      }),
    };
    const engine = new ChineseTitlesEngine(settings, { renameAgent: async () => ({ ok: false, failure: "unused" }) });
    engines.push(engine);
    await engine.usePaseo(makePaseo(state));
    await engine.onTurnAfter("a2", "t2", makePaseo(state), true);
    assert.deepEqual(state.writes, []);
    assert.equal(state.workspace.title, FALLBACK);
  });
});

test("a session created after the fallback never reaches the ownership scan", async () => {
  await withSandbox(async (root, engines) => {
    // The fallback was recorded in the early window; this session only
    // appeared later and is the workspace's only session with a user message.
    // It cannot own the first task, so its turn must not even list the
    // workspace's sessions.
    const late = makeAgent("a2", SESSION_TITLE, "2026-01-02T05:00:00.000Z");
    const state = makeState([late]);
    const { ChineseTitlesEngine } = await import("../server/engine.ts");
    await writeState(
      root,
      { w1: fallbackState() },
      { a2: { status: "done", at: "2026-01-02T05:00:05.000Z", title: SESSION_TITLE, attempts: 1, workspaceId: "w1" } },
    );
    const settings = {
      read: async () => ({
        status: "ready",
        revision: "r1",
        values: settingsSchema.parse({ autoNameProjects: false, autoNameWorkspaces: true, autoNameSessions: false }),
      }),
    };
    const engine = new ChineseTitlesEngine(settings, { renameAgent: async () => ({ ok: false, failure: "unused" }) });
    engines.push(engine);
    await engine.usePaseo(makePaseo(state));
    await engine.onTurnAfter("a2", "t2", makePaseo(state), true);
    assert.deepEqual(state.writes, []);
    assert.equal(state.workspace.title, FALLBACK);
    // No session-list read was needed: the timestamp check rejected it first.
    assert.equal(state.agentListCalls ?? 0, 0);
  });
});

test("with no verified session title, the first-task owner retries the model once on a later turn", async () => {
  await withSandbox(async (root, engines) => {
    const state = makeState([makeAgent("a1", FIRST_TASK, "2026-01-02T03:04:02.000Z")]);
    const paseo = makePaseo(state);
    let modelCalls = 0;
    const withModel = {
      ...paseo,
      config: { get: async () => ({ config: { providers: { cchp: { extends: "codex", label: "CCHP" } } } }) },
      providers: {
        snapshot: async () => ({
          entries: [{ provider: "cchp", status: "ready", enabled: true, models: [{ id: "m1", label: "M", isDefault: true }] }],
        }),
        listModels: async () => ({ models: [] }),
      },
      workspaces: {
        ...paseo.workspaces,
        create: async () => ({
          agents: {
            create: async () => ({
              run: async () => {
                modelCalls += 1;
                return { status: "idle", lastMessage: "梳理需求清单并规划实施步骤" };
              },
              archive: async () => ({}),
            }),
          },
          archive: async () => ({}),
        }),
      },
    };
    const { ChineseTitlesEngine } = await import("../server/engine.ts");
    await writeState(
      root,
      { w1: fallbackState() },
      { a1: { status: "skipped", at: "2026-01-02T03:04:12.000Z", attempts: 2, lastTurnId: "t1", workspaceId: "w1" } },
    );
    const settings = {
      read: async () => ({
        status: "ready",
        revision: "r1",
        values: settingsSchema.parse({ autoNameProjects: false, autoNameWorkspaces: true, autoNameSessions: true }),
      }),
    };
    const engine = new ChineseTitlesEngine(settings, { renameAgent: async () => ({ ok: false, failure: "unused" }) });
    engines.push(engine);
    await engine.usePaseo(paseo);
    // The turn that produced the fallback itself must not spend the retry.
    await engine.onTurnAfter("a1", "t1", withModel, true);
    assert.deepEqual(state.writes, []);
    assert.equal(modelCalls, 0);
    // A later completed turn does, and only once.
    await engine.onTurnAfter("a1", "t2", withModel, true);
    assert.deepEqual(state.writes, ["梳理需求清单并规划实施步骤"]);
    await engine.onTurnAfter("a1", "t3", withModel, true);
    assert.equal(state.writes.length, 1);
    assert.equal(modelCalls, 1);
  });
});

test("after a spent model retry a later verified session title is still adopted", async () => {
  await withSandbox(async (root, engines) => {
    const state = makeState([makeAgent("a1", SESSION_TITLE, "2026-01-02T03:04:02.000Z")]);
    await runReconcile(
      root,
      engines,
      state,
      { w1: fallbackState({ retryUsed: true }) },
      { a1: { status: "done", at: "2026-01-02T03:04:23.138Z", title: SESSION_TITLE, attempts: 1 } },
    );
    assert.deepEqual(state.writes, [SESSION_TITLE]);
  });
});

test("a hook that spent its model call on the session keeps the workspace retry for a later turn", async () => {
  await withSandbox(async (root, engines) => {
    const state = makeState([makeAgent("a1", FIRST_TASK, "2026-01-02T03:04:02.000Z")]);
    const paseo = makePaseo(state);
    let modelCalls = 0;
    const withModel = {
      ...paseo,
      config: { get: async () => ({ config: { providers: { cchp: { extends: "codex", label: "CCHP" } } } }) },
      providers: {
        snapshot: async () => ({
          entries: [{ provider: "cchp", status: "ready", enabled: true, models: [{ id: "m1", label: "M", isDefault: true }] }],
        }),
        listModels: async () => ({ models: [] }),
      },
      workspaces: {
        ...paseo.workspaces,
        create: async () => ({
          agents: {
            create: async () => ({
              run: async () => {
                modelCalls += 1;
                return { status: "idle", lastMessage: "梳理需求清单并规划实施步骤" };
              },
              archive: async () => ({}),
            }),
          },
          archive: async () => ({}),
        }),
      },
    };
    const { ChineseTitlesEngine } = await import("../server/engine.ts");
    await writeState(
      root,
      { w1: fallbackState() },
      { a1: { status: "pending", at: "2026-01-02T03:04:02.000Z", attempts: 0, lastTurnId: null, workspaceId: "w1" } },
    );
    const settings = {
      read: async () => ({
        status: "ready",
        revision: "r1",
        values: settingsSchema.parse({ autoNameProjects: false, autoNameWorkspaces: true, autoNameSessions: true }),
      }),
    };
    const engine = new ChineseTitlesEngine(settings, {
      renameAgent: async (_values, agentId, title) => {
        const agent = state.agents.find((entry) => entry.id === agentId);
        if (!agent) return { ok: false, failure: "missing" };
        agent.title = title;
        return { ok: true };
      },
    });
    engines.push(engine);
    await engine.usePaseo(paseo);
    // Turn 1: session naming spends the hook's model call, so the workspace
    // adopts the new session title instead of calling the model a second time.
    await engine.onTurnAfter("a1", "t1", withModel, true);
    assert.equal(modelCalls, 1);
    assert.deepEqual(state.writes, ["梳理需求清单并规划实施步骤"]);
    // Nothing further is spent on later turns.
    await engine.onTurnAfter("a1", "t2", withModel, true);
    assert.equal(modelCalls, 1);
    assert.equal(state.writes.length, 1);
  });
});

test("an ordinary turn stops revisiting the workspace once its retry was spent", async () => {
  await withSandbox(async (root, engines) => {
    const state = makeState([makeAgent("a1", FIRST_TASK, "2026-01-02T03:04:02.000Z")]);
    const { ChineseTitlesEngine } = await import("../server/engine.ts");
    await writeState(
      root,
      { w1: fallbackState({ retryUsed: true }) },
      { a1: { status: "skipped", at: "2026-01-02T03:04:12.000Z", attempts: 2, lastTurnId: "t1", workspaceId: "w1" } },
    );
    const settings = {
      read: async () => ({
        status: "ready",
        revision: "r1",
        values: settingsSchema.parse({ autoNameProjects: false, autoNameWorkspaces: true, autoNameSessions: true }),
      }),
    };
    const engine = new ChineseTitlesEngine(settings, { renameAgent: async () => ({ ok: false, failure: "unused" }) });
    engines.push(engine);
    await engine.usePaseo(makePaseo(state));
    await engine.onTurnAfter("a1", "t5", makePaseo(state), true);
    assert.deepEqual(state.writes, []);
    assert.equal(state.workspace.title, FALLBACK);
  });
});
