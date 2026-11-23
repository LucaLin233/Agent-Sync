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
    workspaceDirectory: "/tmp/synthetic-workspace",
    name: "synthetic-workspace",
    title: "Extend workspace usage plugin",
    background: false,
    metadata: {},
    archivingAt: null,
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
        assert.equal(id, state.workspace.id);
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
    listAgents: async () => [{
      id: "a1",
      workspaceId: state.workspace.id,
      background: false,
      cwd: state.workspace.workspaceDirectory,
      labels: {},
      lastUserMessageAt: "2026-11-23T00:00:00.000Z",
    }],
    readFirstPrompt: async () => ({
      text: "Fix login bug",
      turnId: "t1",
      at: "2026-11-23T00:00:00.000Z",
    }),
    generate: async () => ({ title: "修复登录问题", source: "model" }),
    ...overrides,
  };
}

test("legacy English workspace can be regenerated repeatedly", async () => {
  const state = { workspace: makeWorkspace(), writes: [] };
  const paseo = makePaseo(state);
  const titles = ["修复登录问题", "处理登录流程"];
  let call = 0;
  const options = optionsFor(paseo, state, {
    generate: async () => ({ title: titles[call++], source: "model" }),
  });
  assert.deepEqual(await regenerateWorkspaceTitle(options), { status: "done", title: "修复登录问题" });
  assert.deepEqual(await regenerateWorkspaceTitle(options), { status: "done", title: "处理登录流程" });
  assert.deepEqual(state.writes, titles);
});

test("manual button works when autoNameWorkspaces is disabled", async () => {
  const state = { workspace: makeWorkspace(), writes: [] };
  const options = optionsFor(makePaseo(state), state, {
    settings: settingsSchema.parse({ autoNameWorkspaces: false }),
  });
  assert.equal((await regenerateWorkspaceTitle(options)).status, "done");
  assert.deepEqual(state.writes, ["修复登录问题"]);
});

test("a manual rename during generation wins and is never overwritten", async () => {
  const state = { workspace: makeWorkspace(), writes: [] };
  const options = optionsFor(makePaseo(state), state, {
    generate: async () => {
      state.workspace.title = "手工标题";
      return { title: "修复登录问题", source: "model" };
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
    generate: async () => {
      await gate;
      return { title: "修复登录问题", source: "model" };
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
    generate: () => generation,
    deadlineAt: Date.now() + 60,
    generationTimeoutMs: 20,
  });
  assert.deepEqual(await regenerateWorkspaceTitle(options), { status: "error", reason: "timeout" });
  release({ title: "修复登录问题", source: "model" });
  await new Promise((resolve) => setTimeout(resolve, 30));
  assert.deepEqual(state.writes, []);
});

test("background and helper workspaces are skipped", async () => {
  const state = { workspace: makeWorkspace({ background: true }), writes: [] };
  const options = optionsFor(makePaseo(state), state);
  assert.deepEqual(await regenerateWorkspaceTitle(options), { status: "skipped", reason: "excluded" });
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

test("model output with ordinary English is rejected and replaced by Chinese fallback", async () => {
  const state = { workspace: makeWorkspace(), writes: [] };
  const options = optionsFor(makePaseo(state), state, {
    generate: async () => ({ title: "修复 LOGIN BUG.", source: "model" }),
  });
  assert.deepEqual(await regenerateWorkspaceTitle(options), { status: "done", title: "修复登录问题" });
  assert.deepEqual(state.writes, ["修复登录问题"]);
});

test("an archived snapshot after generation is not written", async () => {
  const state = { workspace: makeWorkspace(), writes: [] };
  const options = optionsFor(makePaseo(state), state, {
    generate: async () => {
      state.workspace.archivingAt = "2026-11-23T00:00:01.000Z";
      return { title: "修复登录问题", source: "model" };
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
