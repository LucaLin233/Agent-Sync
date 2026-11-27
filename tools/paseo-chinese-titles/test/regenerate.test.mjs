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
    title: "Extend workspace usage plugin",
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

function makeState(workspace = {}) {
  return { workspace: makeWorkspace(workspace), writes: [], sessionWrites: [] };
}

function makePaseo(state) {
  const handle = {
    refresh: async () => ({ ...state.workspace }),
    setTitle: async (title) => {
      state.writes.push(title);
      state.workspace.title = title;
      if (state.onWorkspaceWrite) state.onWorkspaceWrite(title);
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
    agents: {
      ref: (id) => ({
        refresh: async () => {
          const agent = state.agents?.find((entry) => entry.id === id);
          return agent ? { agent: { ...agent } } : null;
        },
      }),
    },
  };
}

function optionsFor(paseo, state, overrides = {}) {
  state.agents ??= [makeAgent()];
  return {
    paseo,
    settings: settingsSchema.parse({}),
    workspaceId: state.workspace.id,
    claims: new Set(),
    agentClaims: new Set(),
    listAgents: async () => state.agents,
    readConversation: async () => ({ text: "用户：修复登录问题\n\n助手：已修复。", turns: 1 }),
    generateConversation: async () => ({ title: "修复登录问题" }),
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

test("a single eligible session is used without an explicit choice and repeated clicks work", async () => {
  const state = makeState();
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
  assert.deepEqual(await regenerateWorkspaceTitle(options), {
    status: "done", title: "修复登录问题", workspaceUpdated: true, sessionUpdated: false, agentId: "a1",
  });
  assert.deepEqual(await regenerateWorkspaceTitle(options), {
    status: "done", title: "登录流程排查", workspaceUpdated: true, sessionUpdated: false, agentId: "a1",
  });
  assert.deepEqual(state.writes, titles);
  assert.deepEqual(read, ["a1", "a1"]);
});

test("two sessions need an explicit pick; only the chosen session is read", async () => {
  const state = makeState();
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
  assert.deepEqual(await regenerateWorkspaceTitle(options), {
    status: "needs_selection", reason: "choose_session", workspaceUpdated: false, sessionUpdated: false,
  });
  assert.deepEqual(read, []);
  assert.deepEqual(await regenerateWorkspaceTitle({ ...options, agentId: "second" }), {
    status: "done", title: "修复登录问题", workspaceUpdated: true, sessionUpdated: false, agentId: "second",
  });
  assert.deepEqual(read, ["second"]);
  assert.deepEqual(state.writes, ["修复登录问题"]);
});

test("an agent from another workspace or a helper session is rejected, not silently substituted", async () => {
  const state = makeState();
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
  for (const agentId of ["other", "helper", "sub", "hidden"]) {
    assert.deepEqual(
      await regenerateWorkspaceTitle({ ...options, agentId }),
      { status: "skipped", reason: "session_not_selectable", workspaceUpdated: false, sessionUpdated: false },
    );
  }
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
    const state = makeState();
    const options = optionsFor(makePaseo(state), state, { generateConversation: run });
    const result = await regenerateWorkspaceTitle(options);
    assert.equal(result.status, "error");
    assert.deepEqual(state.writes, []);
    assert.equal(state.workspace.title, "Extend workspace usage plugin");
  }
});

test("a conversation read failure is reported, not replaced by a fallback title", async () => {
  const state = makeState();
  let generated = 0;
  const options = optionsFor(makePaseo(state), state, {
    readConversation: async () => null,
    generateConversation: async () => {
      generated += 1;
      return { title: "修复登录问题" };
    },
  });
  assert.deepEqual(await regenerateWorkspaceTitle(options), {
    status: "skipped", reason: "conversation_unavailable", workspaceUpdated: false, sessionUpdated: false, agentId: "a1",
  });
  assert.equal(generated, 0);
  assert.deepEqual(state.writes, []);
});

test("an empty conversation or no eligible session is never written", async () => {
  const state = makeState();
  let generated = 0;
  const empty = optionsFor(makePaseo(state), state, {
    readConversation: async () => ({ text: "   ", turns: 0 }),
    generateConversation: async () => {
      generated += 1;
      return { title: "修复登录问题" };
    },
  });
  assert.deepEqual(await regenerateWorkspaceTitle(empty), {
    status: "skipped", reason: "empty_conversation", workspaceUpdated: false, sessionUpdated: false, agentId: "a1",
  });
  const none = optionsFor(makePaseo(state), state, {
    listAgents: async () => [makeAgent({ background: true })],
    generateConversation: async () => {
      generated += 1;
      return { title: "修复登录问题" };
    },
  });
  assert.deepEqual(await regenerateWorkspaceTitle(none), {
    status: "needs_selection", reason: "no_session", workspaceUpdated: false, sessionUpdated: false,
  });
  assert.equal(generated, 0);
  assert.deepEqual(state.writes, []);
});

test("a manual rename during generation wins and is never overwritten", async () => {
  const state = makeState();
  const options = optionsFor(makePaseo(state), state, {
    generateConversation: async () => {
      state.workspace.title = "手工标题";
      return { title: "修复登录问题" };
    },
  });
  assert.deepEqual(await regenerateWorkspaceTitle(options), {
    status: "skipped", reason: "manual_change", workspaceUpdated: false, sessionUpdated: false, agentId: "a1",
  });
  assert.deepEqual(state.writes, []);
  assert.equal(state.workspace.title, "手工标题");
});

test("a second click while generation runs is busy and can retry afterwards", async () => {
  const state = makeState();
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const options = optionsFor(makePaseo(state), state, {
    generateConversation: async () => {
      await gate;
      return { title: "修复登录问题" };
    },
  });
  const first = regenerateWorkspaceTitle(options);
  assert.equal((await regenerateWorkspaceTitle(options)).status, "busy");
  release();
  assert.equal((await first).status, "done");
  assert.deepEqual(state.writes, ["修复登录问题"]);
  assert.equal((await regenerateWorkspaceTitle(options)).status, "done");
});

test("a timed-out RPC never writes afterwards", async () => {
  const state = makeState();
  let release;
  const generation = new Promise((resolve) => { release = resolve; });
  const options = optionsFor(makePaseo(state), state, {
    generateConversation: () => generation,
    deadlineAt: Date.now() + 60,
    generationTimeoutMs: 20,
  });
  assert.equal((await regenerateWorkspaceTitle(options)).reason, "timeout");
  release({ title: "修复登录问题" });
  await new Promise((resolve) => setTimeout(resolve, 30));
  assert.deepEqual(state.writes, []);
});

test("manual generation ignores the automatic baseline and autoNameWorkspaces", async () => {
  const state = makeState();
  const options = optionsFor(makePaseo(state), state, {
    settings: settingsSchema.parse({ autoNameWorkspaces: false, autoNameSessions: false }),
  });
  assert.equal((await regenerateWorkspaceTitle(options)).status, "done");
  assert.deepEqual(state.writes, ["修复登录问题"]);
});

test("background and helper workspaces are skipped", async () => {
  const state = makeState({ background: true });
  assert.deepEqual(
    await regenerateWorkspaceTitle(optionsFor(makePaseo(state), state)),
    { status: "skipped", reason: "excluded", workspaceUpdated: false, sessionUpdated: false },
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
  const state = makeState();
  const options = optionsFor(makePaseo(state), state, {
    generateConversation: async () => {
      state.workspace.archivingAt = "2026-11-23T00:00:01.000Z";
      return { title: "修复登录问题" };
    },
  });
  assert.deepEqual(await regenerateWorkspaceTitle(options), {
    status: "skipped", reason: "not_found", workspaceUpdated: false, sessionUpdated: false, agentId: "a1",
  });
  assert.deepEqual(state.writes, []);
});

test("deadline is checked again after the final refresh", async () => {
  const state = makeState();
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
  assert.equal((await regenerateWorkspaceTitle(options)).reason, "timeout");
  assert.deepEqual(state.writes, []);
});


const SCOPES = ["both", "workspace", "session"];

test("both writes the workspace and the chosen session from one model call", async () => {
  const state = makeState();
  let calls = 0;
  const result = await regenerateWorkspaceTitle(optionsFor(makePaseo(state), state, {
    scope: "both",
    generateConversation: async () => {
      calls += 1;
      return { title: "修复登录问题" };
    },
  }));
  assert.equal(calls, 1, "one model call for two targets");
  assert.deepEqual(result, {
    status: "done",
    title: "修复登录问题",
    workspaceUpdated: true,
    sessionUpdated: true,
    agentId: "a1",
  });
  assert.deepEqual(state.writes, ["修复登录问题"]);
  assert.deepEqual(state.sessionWrites, ["修复登录问题"]);
  assert.equal(state.workspace.title, "修复登录问题");
  assert.equal(state.agents[0].title, "修复登录问题");
});

test("workspace-only mode leaves the session title untouched", async () => {
  const state = makeState();
  const result = await regenerateWorkspaceTitle(optionsFor(makePaseo(state), state, { scope: "workspace" }));
  assert.equal(result.status, "done");
  assert.equal(result.workspaceUpdated, true);
  assert.equal(result.sessionUpdated, false);
  assert.deepEqual(state.writes, ["修复登录问题"]);
  assert.deepEqual(state.sessionWrites, []);
  assert.equal(state.agents[0].title, "Extend workspace usage plugin");
});

test("session-only mode leaves the workspace title and its state untouched", async () => {
  const state = makeState();
  const claims = new Set();
  const result = await regenerateWorkspaceTitle(optionsFor(makePaseo(state), state, {
    scope: "session",
    claims,
  }));
  assert.equal(result.status, "done");
  assert.equal(result.workspaceUpdated, false);
  assert.equal(result.sessionUpdated, true);
  assert.deepEqual(state.writes, []);
  assert.deepEqual(state.sessionWrites, ["修复登录问题"]);
  assert.equal(state.workspace.title, "Extend workspace usage plugin");
  assert.equal(claims.has("w1"), false, "session-only does not claim or block the workspace");
});

test("omitting scope keeps the previous workspace-only behaviour", async () => {
  const state = makeState();
  const result = await regenerateWorkspaceTitle(optionsFor(makePaseo(state), state));
  assert.equal(result.status, "done");
  assert.equal(result.workspaceUpdated, true);
  assert.equal(result.sessionUpdated, false);
  assert.deepEqual(state.sessionWrites, []);
});

test("multiple sessions still require an explicit pick in every scope", async () => {
  for (const scope of SCOPES) {
    const state = makeState();
    state.agents = [makeAgent({ id: "first" }), makeAgent({ id: "second" })];
    let calls = 0;
    const options = optionsFor(makePaseo(state), state, {
      scope,
      generateConversation: async () => {
        calls += 1;
        return { title: "修复登录问题" };
      },
    });
    assert.deepEqual(await regenerateWorkspaceTitle(options), { status: "needs_selection", reason: "choose_session", workspaceUpdated: false, sessionUpdated: false });
    const chosen = await regenerateWorkspaceTitle({ ...options, agentId: "second" });
    assert.equal(chosen.status, "done");
    assert.equal(chosen.agentId, "second");
    assert.equal(calls, 1);
    assert.deepEqual(state.writes, scope === "session" ? [] : ["修复登录问题"]);
    assert.deepEqual(state.sessionWrites, scope === "workspace" ? [] : ["修复登录问题"]);
    const first = state.agents.find((agent) => agent.id === "first");
    assert.equal(first.title, "Extend workspace usage plugin", "unselected sessions are never written");
  }
});

test("the single session is preselected without touching other sessions", async () => {
  const state = makeState();
  state.agents = [makeAgent(), makeAgent({ id: "bg", background: true })];
  const result = await regenerateWorkspaceTitle(optionsFor(makePaseo(state), state, { scope: "session" }));
  assert.equal(result.agentId, "a1");
  assert.deepEqual(state.sessionWrites, ["修复登录问题"]);
  assert.equal(state.agents.find((agent) => agent.id === "bg").title, "Extend workspace usage plugin");
});

test("a model failure writes neither target", async () => {
  for (const scope of SCOPES) {
    const state = makeState();
    const result = await regenerateWorkspaceTitle(optionsFor(makePaseo(state), state, {
      scope,
      generateConversation: async () => ({ title: null, errorCode: "invalid_title" }),
    }));
    assert.equal(result.status, "error");
    assert.equal(result.reason, "invalid_title");
    assert.equal(result.workspaceUpdated, false);
    assert.equal(result.sessionUpdated, false);
    assert.deepEqual(state.writes, []);
    assert.deepEqual(state.sessionWrites, []);
  }
});

test("an unfixable summary title reports rewrite_failed and writes nothing", async () => {
  for (const reason of ["rewrite_failed", "timeout"]) {
    for (const scope of SCOPES) {
      const state = makeState();
      const result = await regenerateWorkspaceTitle(optionsFor(makePaseo(state), state, {
        scope,
        generateConversation: async () => ({ title: null, errorCode: reason }),
      }));
      assert.equal(result.status, "error");
      assert.equal(result.reason, reason);
      assert.equal(result.workspaceUpdated, false);
      assert.equal(result.sessionUpdated, false);
      assert.deepEqual(state.writes, []);
      assert.deepEqual(state.sessionWrites, []);
    }
  }
});

test("a manual workspace rename during generation protects both targets", async () => {
  const state = makeState();
  const result = await regenerateWorkspaceTitle(optionsFor(makePaseo(state), state, {
    scope: "both",
    generateConversation: async () => {
      state.workspace.title = "手工标题";
      return { title: "修复登录问题" };
    },
  }));
  assert.deepEqual(result, { status: "skipped", reason: "manual_change", workspaceUpdated: false, sessionUpdated: false, agentId: "a1" });
  assert.deepEqual(state.writes, []);
  assert.deepEqual(state.sessionWrites, []);
  assert.equal(state.workspace.title, "手工标题");
  assert.equal(state.agents[0].title, "Extend workspace usage plugin");
});

test("a manual session rename during generation protects both targets", async () => {
  const state = makeState();
  const result = await regenerateWorkspaceTitle(optionsFor(makePaseo(state), state, {
    scope: "both",
    generateConversation: async () => {
      state.agents[0].title = "手工会话标题";
      return { title: "修复登录问题" };
    },
  }));
  assert.deepEqual(result, { status: "skipped", reason: "session_manual_change", workspaceUpdated: false, sessionUpdated: false, agentId: "a1" });
  assert.deepEqual(state.writes, []);
  assert.deepEqual(state.sessionWrites, []);
  assert.equal(state.agents[0].title, "手工会话标题");
});

test("a session renamed between the workspace write and the CLI is not overwritten", async () => {
  // The first setTitle is the moment between the joint precheck and the CLI
  // re-read; mutating the session there must leave the session untouched.
  const cases = [
    { change: { title: "手工会话标题" }, reason: "session_manual_change", expectedTitle: "手工会话标题" },
    { change: { archivedAt: "2026-11-23T00:00:02.000Z" }, reason: "session_archived", expectedTitle: "Extend workspace usage plugin" },
    { change: { workspaceId: "w2" }, reason: "session_moved", expectedTitle: "Extend workspace usage plugin" },
  ];
  for (const { change, reason, expectedTitle } of cases) {
    const state = makeState();
    state.onWorkspaceWrite = () => Object.assign(state.agents[0], change);
    const result = await regenerateWorkspaceTitle(optionsFor(makePaseo(state), state, { scope: "both" }));
    assert.equal(result.status, "partial", reason);
    assert.equal(result.reason, reason);
    assert.equal(result.workspaceUpdated, true);
    assert.equal(result.sessionUpdated, false);
    assert.deepEqual(state.writes, ["修复登录问题"]);
    assert.deepEqual(state.sessionWrites, []);
    assert.equal(state.workspace.title, "修复登录问题");
    assert.equal(state.agents[0].title, expectedTitle);
  }
});

test("a failed session rename after the workspace write is a retryable partial result", async () => {
  const state = makeState();
  const result = await regenerateWorkspaceTitle(optionsFor(makePaseo(state), state, {
    scope: "both",
    renameSession: async () => ({ ok: false, failure: "timeout" }),
  }));
  assert.equal(result.status, "partial");
  assert.equal(result.reason, "session_write_failed");
  assert.equal(result.workspaceUpdated, true);
  assert.equal(result.sessionUpdated, false);
  assert.deepEqual(state.writes, ["修复登录问题"]);
  assert.equal(state.workspace.title, "修复登录问题");
  assert.equal(state.agents[0].title, "Extend workspace usage plugin");

  // A retry with a working CLI updates the session; the workspace write is
  // simply repeated with the same value.
  const retry = await regenerateWorkspaceTitle(optionsFor(makePaseo(state), state, { scope: "both" }));
  assert.equal(retry.status, "done");
  assert.equal(state.agents[0].title, "修复登录问题");
});

test("a failed workspace write still renames the chosen session and reports partial", async () => {
  const state = makeState();
  const paseo = makePaseo(state);
  const original = paseo.workspaces.ref;
  paseo.workspaces.ref = (id) => {
    const handle = original(id);
    return { ...handle, setTitle: async () => { throw new Error("synthetic daemon failure"); } };
  };
  const result = await regenerateWorkspaceTitle(optionsFor(paseo, state, { scope: "both" }));
  assert.equal(result.status, "partial");
  assert.equal(result.reason, "workspace_write_failed");
  assert.equal(result.workspaceUpdated, false);
  assert.equal(result.sessionUpdated, true);
  assert.equal(state.workspace.title, "Extend workspace usage plugin");
  assert.equal(state.agents[0].title, "修复登录问题");
});

test("a second click is busy for the same workspace and the same session", async () => {
  const state = makeState();
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const options = optionsFor(makePaseo(state), state, {
    scope: "both",
    generateConversation: async () => {
      await gate;
      return { title: "修复登录问题" };
    },
  });
  const first = regenerateWorkspaceTitle(options);
  assert.equal((await regenerateWorkspaceTitle(options)).status, "busy");
  release();
  assert.equal((await first).status, "done");

  // A concurrent automatic session naming holds the same agent claim.
  const agentClaims = new Set(["a1"]);
  const held = optionsFor(makePaseo(state), state, { scope: "session", agentClaims });
  assert.equal((await regenerateWorkspaceTitle(held)).status, "busy");
  assert.deepEqual(state.sessionWrites, ["修复登录问题"]);
});

test("a partly read session still writes, and reports why coverage is incomplete", async () => {
  const state = makeState();
  const result = await regenerateWorkspaceTitle(optionsFor(makePaseo(state), state, {
    scope: "session",
    readConversation: async () => ({
      text: "用户：开场\n\n助手：部分结论",
      turns: 9,
      segments: ["用户：开场\n\n助手：部分结论"],
      coveredTurns: 3,
      coverage: { kind: "partial", reason: "reset" },
    }),
    generateConversation: async () => ({ title: "概括已读到的会话部分" }),
  }));
  assert.equal(result.status, "done");
  assert.equal(result.sessionUpdated, true);
  assert.deepEqual(result.coverage, { kind: "partial", reason: "reset", turns: 3 });
  assert.deepEqual(state.sessionWrites, ["概括已读到的会话部分"]);
});

test("a full read carries no coverage caveat", async () => {
  const state = makeState();
  const result = await regenerateWorkspaceTitle(optionsFor(makePaseo(state), state, {
    scope: "session",
    readConversation: async () => ({
      text: "用户：完整会话",
      turns: 1,
      segments: ["用户：完整会话"],
      coveredTurns: 1,
      coverage: { kind: "full" },
    }),
    generateConversation: async () => ({ title: "完整会话标题" }),
  }));
  assert.equal(result.status, "done");
  assert.equal(result.coverage, undefined);
});

test("a timeout before the writes leaves every title untouched", async () => {
  const state = makeState();
  let release;
  const generation = new Promise((resolve) => { release = resolve; });
  const result = await regenerateWorkspaceTitle(optionsFor(makePaseo(state), state, {
    scope: "both",
    generateConversation: () => generation,
    deadlineAt: Date.now() + 60,
    generationTimeoutMs: 20,
  }));
  assert.equal(result.status, "error");
  assert.equal(result.reason, "timeout");
  release({ title: "修复登录问题" });
  await new Promise((resolve) => setTimeout(resolve, 30));
  assert.deepEqual(state.writes, []);
  assert.deepEqual(state.sessionWrites, []);
});

test("both writes the same truncated summary to each target", async () => {
  const state = makeState();
  const long = "修复登录问题并补充会话摘要的并发保护逻辑说明";
  const result = await regenerateWorkspaceTitle(optionsFor(makePaseo(state), state, {
    scope: "both",
    settings: settingsSchema.parse({ titleMaxChars: 8 }),
    generateConversation: async () => ({ title: long }),
  }));
  assert.equal(result.status, "done");
  assert.equal(result.title, state.writes[0]);
  assert.deepEqual(state.sessionWrites, [state.writes[0]]);
  assert.ok(Array.from(state.writes[0]).length <= 8);
  assert.equal(state.workspace.title, state.writes[0]);
  assert.equal(state.agents[0].title, state.writes[0]);
});

test("session-only mode on an archived workspace writes nothing", async () => {
  const state = makeState();
  state.workspace.archivingAt = "2026-11-23T00:00:02.000Z";
  const result = await regenerateWorkspaceTitle(optionsFor(makePaseo(state), state, { scope: "session" }));
  assert.equal(result.status, "skipped");
  assert.equal(result.reason, "not_found");
  assert.deepEqual(state.sessionWrites, []);
});

test("the start RPC accepts old requests, the three scopes and the status contract", async () => {
  const { regenerationStatusRpc, startRegenerationRpc } = await import("../shared/rpc.ts");
  assert.deepEqual(startRegenerationRpc.input.parse({ workspaceId: "w1" }), { workspaceId: "w1" });
  for (const scope of ["both", "workspace", "session"]) {
    assert.equal(startRegenerationRpc.input.parse({ workspaceId: "w1", agentId: "a1", scope }).scope, scope);
  }
  assert.throws(() => startRegenerationRpc.input.parse({ workspaceId: "w1", scope: "all" }));
  assert.deepEqual(startRegenerationRpc.output.parse({ status: "busy" }), { status: "busy" });
  assert.deepEqual(startRegenerationRpc.output.parse({ status: "started", jobId: "rg_1" }), {
    status: "started",
    jobId: "rg_1",
  });

  // A finished job carries the same per-target result the old synchronous RPC
  // returned; the status call itself stays small.
  const partial = {
    status: "partial",
    title: "修复登录问题",
    reason: "session_write_failed",
    workspaceUpdated: true,
    sessionUpdated: false,
  };
  assert.deepEqual(
    regenerationStatusRpc.output.parse({ status: "done", jobId: "rg_1", result: partial }),
    { status: "done", jobId: "rg_1", result: partial },
  );
  assert.deepEqual(regenerationStatusRpc.output.parse({ status: "unknown" }), { status: "unknown" });
  assert.deepEqual(regenerationStatusRpc.output.parse({ status: "running", jobId: "rg_1" }), {
    status: "running",
    jobId: "rg_1",
  });
  assert.throws(() => regenerationStatusRpc.output.parse({ status: "done", jobId: "rg_1" }));
  assert.throws(() => regenerationStatusRpc.input.parse({}));
});

test("a job registry reports running, done and busy, and drops a disposed job's result", async () => {
  const { RegenerationJobs } = await import("../server/regeneration-jobs.ts");
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  let probe = null;
  const jobs = new RegenerationJobs({ id: () => "rg_test" });
  const started = jobs.start({ workspaceId: "w1", claimKey: "workspace:w1" }, async (isCancelled) => {
    probe = isCancelled;
    await gate;
    return { status: "done", title: "修复登录问题", workspaceUpdated: true, sessionUpdated: false };
  });
  assert.deepEqual(started, { status: "started", jobId: "rg_test" });
  assert.deepEqual(jobs.start({ workspaceId: "w1", claimKey: "workspace:w1" }, async () => ({ status: "error", workspaceUpdated: false, sessionUpdated: false })), { status: "busy" });
  assert.deepEqual(jobs.status({ jobId: "rg_test" }), { status: "running", jobId: "rg_test" });
  assert.deepEqual(jobs.status({ workspaceId: "w1" }), { status: "running", jobId: "rg_test" });
  assert.equal(probe(), false);
  release();
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.deepEqual(jobs.status({ jobId: "rg_test" }), {
    status: "done",
    jobId: "rg_test",
    result: { status: "done", title: "修复登录问题", workspaceUpdated: true, sessionUpdated: false },
  });
  assert.deepEqual(jobs.status({ jobId: "missing" }), { status: "unknown" });

  // A second workspace is independent, so two workspaces may run at once.
  const other = jobs.start({ workspaceId: "w2", claimKey: "workspace:w2" }, async () => ({ status: "error", workspaceUpdated: false, sessionUpdated: false }));
  assert.equal(other.status, "started");

  jobs.dispose();
  assert.deepEqual(jobs.status({ jobId: "rg_test" }), { status: "unknown" });
  assert.deepEqual(jobs.start({ workspaceId: "w3", claimKey: "workspace:w3" }, async () => ({ status: "error", workspaceUpdated: false, sessionUpdated: false })), { status: "busy" });
});

test("a disposed job never lets its late result through", async () => {
  const { RegenerationJobs } = await import("../server/regeneration-jobs.ts");
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const jobs = new RegenerationJobs({ id: () => "rg_late" });
  jobs.start({ workspaceId: "w1", claimKey: "workspace:w1" }, async () => {
    await gate;
    return { status: "done", title: "修复登录问题", workspaceUpdated: true, sessionUpdated: false };
  });
  jobs.dispose();
  release();
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.deepEqual(jobs.status({ jobId: "rg_late" }), { status: "unknown" });
});

test("a workspace write failure is not downgraded when the session then changes", async () => {
  const state = makeState();
  // The workspace write fails, and the session is renamed by a user right after.
  state.onWorkspaceWrite = () => undefined;
  const paseo = makePaseo(state);
  const original = paseo.workspaces.ref;
  paseo.workspaces.ref = (id) => {
    const handle = original(id);
    return {
      ...handle,
      setTitle: async () => {
        state.agents[0].title = "手工会话标题";
        throw new Error("synthetic daemon failure");
      },
    };
  };
  const result = await regenerateWorkspaceTitle(optionsFor(paseo, state, { scope: "both" }));
  assert.equal(result.status, "error");
  assert.equal(result.reason, "workspace_write_failed");
  assert.equal(result.workspaceUpdated, false);
  assert.equal(result.sessionUpdated, false);
  assert.deepEqual(state.sessionWrites, []);
  assert.equal(state.agents[0].title, "手工会话标题");
});

for (const reason of ["timeout", "helper_failed"]) {
  test(`a failed manual job (${reason}) logs one single-argument JSON diagnostic keyed by its jobId, without text`, async (t) => {
    const { RegenerationJobs } = await import("../server/regeneration-jobs.ts");
    const warn = t.mock.method(console, "warn", () => {});
    let clock = 1_000;
    const jobs = new RegenerationJobs({ id: () => "rg_diag", now: () => clock });
    jobs.start({ workspaceId: "w1", claimKey: "workspace:w1" }, async () => {
      clock += 42_000;
      return {
        status: "error",
        reason,
        agentId: "a1",
        title: "合成标题正文",
        workspaceUpdated: false,
        sessionUpdated: false,
      };
    });
    await new Promise((resolve) => setTimeout(resolve, 0));
    assert.equal(warn.mock.callCount(), 1);
    const args = warn.mock.calls[0].arguments;
    assert.equal(args.length, 1);
    const line = args[0];
    const prefix = "[paseo-chinese-titles] regeneration job failed ";
    assert.equal(line.startsWith(prefix), true);
    assert.deepEqual(JSON.parse(line.slice(prefix.length)), {
      jobId: "rg_diag",
      workspaceId: "w1",
      agentId: "a1",
      status: "error",
      reason,
      elapsedMs: 42_000,
    });
    assert.equal(line.includes("合成标题正文"), false);
  });
}

test("a job whose run throws logs internal_failed once, without the raw error", async (t) => {
  const { RegenerationJobs } = await import("../server/regeneration-jobs.ts");
  const warn = t.mock.method(console, "warn", () => {});
  const jobs = new RegenerationJobs({ id: () => "rg_throw" });
  jobs.start({ workspaceId: "w2", claimKey: "workspace:w2" }, async () => {
    throw new Error("synthetic raw failure text");
  });
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(warn.mock.callCount(), 1);
  const args = warn.mock.calls[0].arguments;
  assert.equal(args.length, 1);
  const fields = JSON.parse(args[0].slice("[paseo-chinese-titles] regeneration job failed ".length));
  assert.equal(fields.jobId, "rg_throw");
  assert.equal(fields.workspaceId, "w2");
  assert.equal(fields.reason, "internal_failed");
  assert.equal(fields.status, "error");
  assert.equal(args[0].includes("synthetic raw failure text"), false);
});

const LOG_PREFIX = "[paseo-chinese-titles] regeneration job failed ";

/** Captures console.warn for one job and returns the single parsed line. */
async function captureFailure(run) {
  const lines = [];
  const original = console.warn;
  console.warn = (...args) => { lines.push(args); };
  try {
    await run();
    // The job runs detached from start(); wait for its one line instead of
    // guessing a number of ticks.
    const until = Date.now() + 2_000;
    while (lines.length === 0 && Date.now() < until) {
      await new Promise((resolve) => setTimeout(resolve, 5));
    }
    await new Promise((resolve) => setImmediate(resolve));
  } finally {
    console.warn = original;
  }
  assert.equal(lines.length, 1, `exactly one diagnostic line, saw ${lines.length}`);
  assert.equal(lines[0].length, 1, "one string argument");
  assert.equal(typeof lines[0][0], "string");
  assert.equal(lines[0][0].startsWith(LOG_PREFIX), true);
  return JSON.parse(lines[0][0].slice(LOG_PREFIX.length));
}

async function runManualJob(jobId, overrides) {
  const { RegenerationJobs } = await import("../server/regeneration-jobs.ts");
  const { regenerateWorkspaceTitle } = await import("../server/regenerate.ts");
  const { paseoOverride, ...rest } = overrides;
  const jobs = new RegenerationJobs({ id: () => jobId });
  const diagnostics = {};
  jobs.start({ workspaceId: "w1", claimKey: "workspace:w1", diagnostics }, async (isCancelled) => {
    const state = makeState();
    const paseo = paseoOverride ? paseoOverride(state) : makePaseo(state);
    return regenerateWorkspaceTitle({
      ...optionsFor(paseo, state, { agentId: "a1" }),
      isCancelled,
      diagnostics,
      ...rest,
    });
  });
}

test("two different timeout stages are distinguishable and keep the selected session", async () => {
  // Stage A: no budget left before the conversation is read.
  const base = 1_000;
  const early = await captureFailure(() => runManualJob("rg_early", {
    scope: "session",
    deadlineAt: base + 5_000,
    now: () => base + 5_000,
    readConversation: async () => {
      throw new Error("must not read: the budget is already spent");
    },
  }));
  assert.equal(early.reason, "timeout");
  assert.equal(early.stage, "conversation_read");
  assert.equal(early.agentId, "a1", "the selection survives an early return without agentId");
  assert.equal(early.jobId, "rg_early");
  assert.equal(early.workspaceId, "w1");
  assert.equal(typeof early.budgetMs, "number");

  // Stage B: the model step is what ran out of time.
  let clock = 10_000;
  const model = await captureFailure(() => runManualJob("rg_model", {
    scope: "session",
    deadlineAt: 40_000,
    now: () => clock,
    generateConversation: () => {
      clock = 40_000; // the deadline passes while the model is working
      return new Promise(() => {}); // never settles: the budget check ends the run
    },
  }));
  assert.equal(model.reason, "timeout");
  assert.equal(model.stage, "model_generation");
  assert.equal(model.agentId, "a1");
  assert.equal(model.budgetMs, 24_000, "the model slice that was actually given");
  assert.notEqual(model.stage, early.stage, "two timeout stages are not one bucket");
  assert.equal(model.reason, early.reason, "the controlled reason itself is unchanged");
});

test("a write failure after a successful generation carries no model budget", async () => {
  // The model slice is real and finite; the later write is a different stage.
  // The line must not reuse the model's budget for the write failure.
  const line = await captureFailure(() => runManualJob("rg_write", {
    scope: "workspace",
    generationTimeoutMs: 24_000,
    generateConversation: async () => ({ title: "修复登录问题" }),
    paseoOverride: (state) => {
      const paseo = makePaseo(state);
      const original = paseo.workspaces.ref;
      paseo.workspaces.ref = (id) => ({
        ...original(id),
        setTitle: async () => { throw new Error("synthetic daemon failure"); },
      });
      return paseo;
    },
  }));
  assert.equal(line.jobId, "rg_write");
  assert.equal(line.reason, "workspace_write_failed");
  assert.equal(line.stage, "workspace_write");
  assert.equal(line.agentId, "a1");
  assert.equal("budgetMs" in line, false, `no stale model budget: ${JSON.stringify(line)}`);
  assert.equal(JSON.stringify(line).includes("修复登录问题"), false, "no title text");
});

test("a failure after selection keeps the selected agentId in the line", async () => {
  const line = await captureFailure(() => runManualJob("rg_selected", {
    // No time left once the conversation is in hand: this exit's result carries
    // no agentId, so the line must take it from the run itself.
    deadlineAt: 20_000,
    now: () => 20_000,
    readConversation: async () => null,
  }));
  assert.equal(line.jobId, "rg_selected");
  assert.equal(line.agentId, "a1");
  assert.equal(line.stage, "conversation_read");
  assert.equal(line.reason, "timeout");
  assert.equal(JSON.stringify(line).includes("修复登录问题"), false, "no title text");
});

test("successful, skipped and disposed jobs log nothing", async (t) => {
  const { RegenerationJobs } = await import("../server/regeneration-jobs.ts");
  const warn = t.mock.method(console, "warn", () => {});
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const jobs = new RegenerationJobs({ id: () => "rg_quiet" });
  jobs.start({ workspaceId: "w1", claimKey: "workspace:w1" }, async () => ({ status: "done", title: "修复登录问题", workspaceUpdated: true, sessionUpdated: false }));
  await new Promise((resolve) => setTimeout(resolve, 0));
  jobs.start({ workspaceId: "w2", claimKey: "workspace:w2" }, async () => ({ status: "skipped", reason: "not_found", workspaceUpdated: false, sessionUpdated: false }));
  await new Promise((resolve) => setTimeout(resolve, 0));
  jobs.start({ workspaceId: "w3", claimKey: "workspace:w3" }, async () => {
    await gate;
    return { status: "error", reason: "timeout", workspaceUpdated: false, sessionUpdated: false };
  });
  jobs.dispose();
  release();
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(warn.mock.callCount(), 0);
});
