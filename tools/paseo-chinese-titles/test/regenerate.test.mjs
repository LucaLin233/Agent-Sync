import test from "node:test";
import assert from "node:assert/strict";
import { regenerateWorkspaceTitle } from "../server/regenerate.ts";
import {
  WORKSPACE_SEED_METADATA_KEY,
  planWorkspaceTitleSeed,
  seededWorkspaceTitle,
} from "../server/seed.ts";
import { settingsSchema } from "../shared/settings.ts";

function makeWorkspace(overrides = {}) {
  return {
    id: "w1",
    projectId: "p1",
    projectDisplayName: "项目",
    workspaceDirectory: "/synthetic/workspace",
    name: "synthetic-workspace",
    title: "Extend workspace usage plugin",
    background: false,
    metadata: {},
    archivingAt: null,
    ...overrides,
  };
}

function makeAgent(overrides = {}) {
  return {
    id: "a1",
    workspaceId: "w1",
    background: false,
    cwd: "/synthetic/workspace",
    labels: {},
    metadata: {},
    lastUserMessageAt: "2026-11-23T00:00:00.000Z",
    createdAt: "2026-11-23T00:00:00.000Z",
    updatedAt: "2026-11-23T00:00:00.000Z",
    ...overrides,
  };
}

function makePaseo(state) {
  const handle = {
    refresh: async () => ({ ...state.workspace }),
    setTitle: async (title) => {
      state.writes.push(title);
      state.workspace.title = title;
      return { title };
    },
  };
  return {
    workspaces: {
      ref: (id) => {
        assert.equal(id, state.workspace.id, "only the requested workspace is touched");
        return handle;
      },
    },
  };
}

function optionsFor(paseo, state, overrides = {}) {
  return {
    paseo,
    settings: settingsSchema.parse({}),
    workspaceId: state.workspace.id,
    claims: new Set(),
    listAgents: async () => [makeAgent()],
    readConversation: async () => ({ text: "用户：修复登录问题\n\n助手：已修复。", turns: 1 }),
    generateConversation: async () => ({ title: "修复登录问题" }),
    ...overrides,
  };
}

test("a single eligible session is used without an explicit choice and repeated clicks work", async () => {
  const state = { workspace: makeWorkspace(), writes: [] };
  const titles = ["修复登录问题", "登录流程排查"];
  let call = 0;
  const read = [];
  const options = optionsFor(makePaseo(state), state, {
    readConversation: async (agentId) => {
      read.push(agentId);
      return { text: "用户：修复登录问题", turns: 1 };
    },
    generateConversation: async () => ({ title: titles[call++] }),
  });
  assert.deepEqual(await regenerateWorkspaceTitle(options), { status: "done", title: "修复登录问题" });
  assert.deepEqual(await regenerateWorkspaceTitle(options), { status: "done", title: "登录流程排查" });
  assert.deepEqual(state.writes, titles);
  assert.deepEqual(read, ["a1", "a1"]);
});

test("two sessions need an explicit pick; only the chosen session is read", async () => {
  const state = { workspace: makeWorkspace(), writes: [] };
  const read = [];
  const agents = [
    makeAgent({ id: "first", lastUserMessageAt: "2026-11-23T00:00:00.000Z" }),
    makeAgent({ id: "second", lastUserMessageAt: "2026-11-23T05:00:00.000Z" }),
  ];
  const options = optionsFor(makePaseo(state), state, {
    listAgents: async () => agents,
    readConversation: async (agentId) => {
      read.push(agentId);
      return { text: `用户：${agentId} 的会话`, turns: 1 };
    },
  });
  assert.deepEqual(await regenerateWorkspaceTitle(options), { status: "needs_selection", reason: "choose_session" });
  assert.deepEqual(read, []);
  assert.deepEqual(await regenerateWorkspaceTitle({ ...options, agentId: "second" }), { status: "done", title: "修复登录问题" });
  assert.deepEqual(read, ["second"]);
  assert.deepEqual(state.writes, ["修复登录问题"]);
});

test("an agent from another workspace or a helper session is rejected, not silently substituted", async () => {
  const state = { workspace: makeWorkspace(), writes: [] };
  const read = [];
  const options = optionsFor(makePaseo(state), state, {
    listAgents: async () => [
      makeAgent({ id: "mine" }),
      makeAgent({ id: "other", workspaceId: "w2" }),
      makeAgent({ id: "helper", labels: { "paseo-chinese-titles.helper": "1" } }),
      makeAgent({ id: "sub", labels: { "paseo.parent-agent-id": "mine" } }),
      makeAgent({ id: "hidden", background: true }),
    ],
    readConversation: async (agentId) => {
      read.push(agentId);
      return { text: "用户：内容", turns: 1 };
    },
  });
  assert.deepEqual(
    await regenerateWorkspaceTitle({ ...options, agentId: "other" }),
    { status: "skipped", reason: "session_not_selectable" },
  );
  assert.deepEqual(
    await regenerateWorkspaceTitle({ ...options, agentId: "helper" }),
    { status: "skipped", reason: "session_not_selectable" },
  );
  assert.deepEqual(
    await regenerateWorkspaceTitle({ ...options, agentId: "sub" }),
    { status: "skipped", reason: "session_not_selectable" },
  );
  assert.deepEqual(
    await regenerateWorkspaceTitle({ ...options, agentId: "hidden" }),
    { status: "skipped", reason: "session_not_selectable" },
  );
  assert.deepEqual(read, []);
  assert.deepEqual(state.writes, []);
});

test("a failed, invalid or timed-out model answer keeps the existing title", async () => {
  for (const run of [
    async () => ({ title: null, errorCode: "model_failed" }),
    async () => ({ title: null, errorCode: "invalid_title" }),
    async () => ({ title: null, errorCode: "provider_unavailable" }),
    async () => null,
  ]) {
    const state = { workspace: makeWorkspace(), writes: [] };
    const options = optionsFor(makePaseo(state), state, { generateConversation: run });
    const result = await regenerateWorkspaceTitle(options);
    assert.equal(result.status, "error");
    assert.deepEqual(state.writes, []);
    assert.equal(state.workspace.title, "Extend workspace usage plugin");
  }
});

test("a conversation read failure is reported, not replaced by a fallback title", async () => {
  const state = { workspace: makeWorkspace(), writes: [] };
  let generated = 0;
  const options = optionsFor(makePaseo(state), state, {
    readConversation: async () => null,
    generateConversation: async () => {
      generated += 1;
      return { title: "修复登录问题" };
    },
  });
  assert.deepEqual(await regenerateWorkspaceTitle(options), { status: "skipped", reason: "conversation_unavailable" });
  assert.equal(generated, 0);
  assert.deepEqual(state.writes, []);
});

test("an empty conversation or no eligible session is never written", async () => {
  const state = { workspace: makeWorkspace(), writes: [] };
  let generated = 0;
  const empty = optionsFor(makePaseo(state), state, {
    readConversation: async () => ({ text: "   ", turns: 0 }),
    generateConversation: async () => {
      generated += 1;
      return { title: "修复登录问题" };
    },
  });
  assert.deepEqual(await regenerateWorkspaceTitle(empty), { status: "skipped", reason: "empty_conversation" });
  const none = optionsFor(makePaseo(state), state, {
    listAgents: async () => [makeAgent({ background: true })],
    generateConversation: async () => {
      generated += 1;
      return { title: "修复登录问题" };
    },
  });
  assert.deepEqual(await regenerateWorkspaceTitle(none), { status: "needs_selection", reason: "no_session" });
  assert.equal(generated, 0);
  assert.deepEqual(state.writes, []);
});

test("a manual rename during generation wins and is never overwritten", async () => {
  const state = { workspace: makeWorkspace(), writes: [] };
  const options = optionsFor(makePaseo(state), state, {
    generateConversation: async () => {
      state.workspace.title = "手工标题";
      return { title: "修复登录问题" };
    },
  });
  assert.deepEqual(await regenerateWorkspaceTitle(options), { status: "skipped", reason: "manual_change" });
  assert.deepEqual(state.writes, []);
  assert.equal(state.workspace.title, "手工标题");
});

test("a second click while generation runs is busy and can retry afterwards", async () => {
  const state = { workspace: makeWorkspace(), writes: [] };
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const options = optionsFor(makePaseo(state), state, {
    generateConversation: async () => {
      await gate;
      return { title: "修复登录问题" };
    },
  });
  const first = regenerateWorkspaceTitle(options);
  assert.deepEqual(await regenerateWorkspaceTitle(options), { status: "busy" });
  release();
  assert.equal((await first).status, "done");
  assert.deepEqual(state.writes, ["修复登录问题"]);
  assert.equal((await regenerateWorkspaceTitle(options)).status, "done");
});

test("a timed-out RPC never writes afterwards", async () => {
  const state = { workspace: makeWorkspace(), writes: [] };
  let release;
  const generation = new Promise((resolve) => { release = resolve; });
  const options = optionsFor(makePaseo(state), state, {
    generateConversation: () => generation,
    deadlineAt: Date.now() + 60,
    generationTimeoutMs: 20,
  });
  assert.deepEqual(await regenerateWorkspaceTitle(options), { status: "error", reason: "timeout" });
  release({ title: "修复登录问题" });
  await new Promise((resolve) => setTimeout(resolve, 30));
  assert.deepEqual(state.writes, []);
});

test("manual generation ignores the automatic baseline and autoNameWorkspaces", async () => {
  const state = { workspace: makeWorkspace(), writes: [] };
  const options = optionsFor(makePaseo(state), state, {
    settings: settingsSchema.parse({ autoNameWorkspaces: false, autoNameSessions: false }),
  });
  assert.equal((await regenerateWorkspaceTitle(options)).status, "done");
  assert.deepEqual(state.writes, ["修复登录问题"]);
});

test("background and helper workspaces are skipped", async () => {
  const state = { workspace: makeWorkspace({ background: true }), writes: [] };
  assert.deepEqual(
    await regenerateWorkspaceTitle(optionsFor(makePaseo(state), state)),
    { status: "skipped", reason: "excluded" },
  );
  assert.deepEqual(state.writes, []);
});

test("workspace creation seed is Chinese, distinct from the prompt title and marked", () => {
  const chinese = planWorkspaceTitleSeed({ prompt: "修复登录问题", maxChars: 28 });
  assert.equal(chinese.title, "工作区 · 修复登录问题");
  assert.notEqual(chinese.title, "修复登录问题");
  assert.equal(chinese.metadata[WORKSPACE_SEED_METADATA_KEY], chinese.title);
  assert.equal(seededWorkspaceTitle(chinese.metadata), chinese.title);

  const english = planWorkspaceTitleSeed({ prompt: "Fix login bug", maxChars: 28 });
  assert.equal(english.title, "修复登录问题");
  assert.ok(english.title.length <= 28);

  assert.equal(planWorkspaceTitleSeed({ title: "手工标题", prompt: "Fix login bug", maxChars: 28 }), null);
  assert.equal(planWorkspaceTitleSeed({ title: "Fix login bug", prompt: "Fix login bug", maxChars: 28 }), null);
  assert.equal(planWorkspaceTitleSeed({ title: "", prompt: "Fix login bug", maxChars: 28 }).title, "修复登录问题");
  assert.equal(planWorkspaceTitleSeed({ prompt: "", maxChars: 28 }), null);
  assert.equal(planWorkspaceTitleSeed({
    prompt: "Fix login bug",
    metadata: { [WORKSPACE_SEED_METADATA_KEY]: "修复登录问题" },
    maxChars: 28,
  }), null);
});

test("an archived workspace after generation is not written", async () => {
  const state = { workspace: makeWorkspace(), writes: [] };
  const options = optionsFor(makePaseo(state), state, {
    generateConversation: async () => {
      state.workspace.archivingAt = "2026-11-23T00:00:01.000Z";
      return { title: "修复登录问题" };
    },
  });
  assert.deepEqual(await regenerateWorkspaceTitle(options), { status: "skipped", reason: "not_found" });
  assert.deepEqual(state.writes, []);
});

test("deadline is checked again after the final refresh", async () => {
  const state = { workspace: makeWorkspace(), writes: [] };
  let clock = 1_000_000;
  let refreshes = 0;
  const handle = {
    refresh: async () => {
      refreshes += 1;
      if (refreshes === 2) clock += 10_000;
      return { ...state.workspace };
    },
    setTitle: async (title) => {
      state.writes.push(title);
      state.workspace.title = title;
      return { title };
    },
  };
  const options = optionsFor({ workspaces: { ref: () => handle } }, state, {
    now: () => clock,
    deadlineAt: 1_010_000,
  });
  assert.deepEqual(await regenerateWorkspaceTitle(options), { status: "error", reason: "timeout" });
  assert.deepEqual(state.writes, []);
});
