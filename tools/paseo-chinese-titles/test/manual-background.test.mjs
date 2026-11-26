import test from "node:test";
import assert from "node:assert/strict";
import { regenerateWorkspaceTitle } from "../server/regenerate.ts";
import { generateConversationTitle, stepTimeoutMs } from "../server/helper.ts";
import { settingsSchema } from "../shared/settings.ts";

/** A synthetic clock the model stub advances by one real observed turn. */
function makeClock(start = 1_000_000) {
  let value = start;
  return {
    now: () => value,
    advance: (ms) => { value += ms; },
  };
}

function conversationPaseo(clock, { answerFor }) {
  const calls = [];
  const paseo = {
    config: { get: async () => ({ config: { providers: { cchp: { extends: "codex", label: "CCHP" } } } }) },
    providers: {
      snapshot: async () => ({
        entries: [{ provider: "cchp", status: "ready", enabled: true, models: [{ id: "m1", label: "M", isDefault: true }] }],
      }),
      listModels: async () => ({ models: [] }),
    },
    workspaces: {
      create: async () => ({
        agents: {
          create: async () => ({
            run: async (prompt, options = {}) => {
              calls.push({ prompt, timeoutMs: options.timeoutMs });
              // The measured helper turn in the report took about 5.15 s.
              clock.advance(5_150);
              return { status: "idle", lastMessage: answerFor(calls.length) };
            },
            archive: async () => ({}),
          }),
        },
        archive: async () => ({}),
      }),
    },
  };
  return { paseo, calls };
}

/**
 * The shipped 0.17.4 behaviour, transcribed from the installed helper.ts
 * (SHA256 b7479958...): a 22 s RPC deadline, a 4.5 s double-write reserve, the
 * remaining time split evenly over the steps, minus 500 ms.
 */
function shippedStepTimeoutMs({ remaining, stepsLeft, totalTimeoutMs = 18_000 }) {
  return Math.min(18_000, totalTimeoutMs, Math.max(1_000, Math.floor(remaining / stepsLeft) - 500));
}

test("the old 22 s RPC share cannot fit the observed 5.15 s first digest", () => {
  // The field runs waited 5154 ms and 5091 ms on the first digest. In the
  // shipped code, after the scan and the 4.5 s double-write reserve, roughly
  // 12.5 s was split over two digests and the synthesis.
  const oldFirstStep = shippedStepTimeoutMs({ remaining: 12_500, stepsLeft: 3 });
  assert.ok(oldFirstStep < 5_150, `old first-step cap was ${oldFirstStep} ms`);
  // The background job's 120 s task deadline keeps every step above the
  // measured turn, even with two digests, one synthesis and one rewrite.
  const newFirstStep = stepTimeoutMs({ remaining: 120_000, stepsLeft: 4, startBudget: 35_000 });
  assert.ok(newFirstStep >= 5_150, `new first-step cap was ${newFirstStep} ms`);
  // The new cap is also bounded, not unbounded: it never exceeds the step max.
  assert.equal(stepTimeoutMs({ remaining: 600_000, stepsLeft: 1, startBudget: 35_000 }), 35_000);
});

test("a long conversation finishes every digest and the synthesis before writing", async () => {
  const clock = makeClock();
  const settings = settingsSchema.parse({});
  const { paseo, calls } = conversationPaseo(clock, {
    answerFor: (index) => index < 3 ? `第 ${index} 段：排查标题超时` : "排查标题超时并改为后台生成",
  });
  const segments = ["用户：第一段\n\n助手：先看同步时限", "用户：第二段\n\n助手：再看分段预算"];
  const startedAt = clock.now();
  const result = await generateConversationTitle(paseo, settings, {
    transcript: segments.join("\n\n"),
    segments,
    maxChars: 28,
  }, {
    timeoutMs: 35_000,
    deadlineAt: startedAt + 120_000,
    now: clock.now,
  });
  assert.deepEqual(result, { title: "排查标题超时并改为后台生成", segments: { total: 2, used: 2 } });
  assert.equal(calls.length, 3, "two digests plus one synthesis");
  for (const call of calls) {
    assert.ok(call.timeoutMs >= 5_150, `step cap ${call.timeoutMs} ms would kill the observed turn`);
  }
});

test("a manual long-conversation job writes both targets with the one summary", async () => {
  const clock = makeClock();
  const settings = settingsSchema.parse({});
  const writes = [];
  const sessionWrites = [];
  const state = {
    workspace: {
      id: "w1",
      projectId: "p1",
      projectDisplayName: "Paseo",
      workspaceDirectory: "/synthetic/workspace",
      name: "synthetic",
      title: "Extend workspace usage plugin",
      background: false,
      metadata: {},
      archivingAt: null,
    },
    agents: [{
      id: "a1",
      workspaceId: "w1",
      title: "Extend workspace usage plugin",
      background: false,
      cwd: "/synthetic/workspace",
      labels: {},
      metadata: {},
      lastUserMessageAt: "2026-11-24T00:00:00.000Z",
      createdAt: "2026-11-24T00:00:00.000Z",
      updatedAt: "2026-11-24T00:00:00.000Z",
    }],
  };
  const paseo = {
    workspaces: {
      ref: (id) => ({
        refresh: async () => (id === state.workspace.id ? { ...state.workspace } : null),
        setTitle: async (title) => {
          writes.push(title);
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
  const { paseo: model, calls } = conversationPaseo(clock, {
    answerFor: (index) => index < 3 ? `第 ${index} 段：排查标题超时` : "排查标题超时并改为后台生成",
  });
  const segments = ["用户：第一段\n\n助手：先看同步时限", "用户：第二段\n\n助手：再看分段预算"];
  const result = await regenerateWorkspaceTitle({
    paseo,
    settings,
    workspaceId: "w1",
    scope: "both",
    claims: new Set(),
    agentClaims: new Set(),
    now: clock.now,
    deadlineAt: clock.now() + 120_000,
    generationTimeoutMs: 35_000,
    listAgents: async () => state.agents,
    readConversation: async () => ({
      text: segments.join("\n\n"),
      turns: 4,
      segments,
      coveredTurns: 4,
      coverage: { kind: "full" },
    }),
    generateConversation: (request, timeoutMs, deadlineAt) =>
      generateConversationTitle(model, settings, request, { timeoutMs, deadlineAt, now: clock.now }),
    renameSession: async (agentId, title) => {
      const agent = state.agents.find((entry) => entry.id === agentId);
      if (!agent) return { ok: false, failure: "failed" };
      sessionWrites.push(title);
      agent.title = title;
      return { ok: true };
    },
  });
  assert.deepEqual(result, {
    status: "done",
    title: "排查标题超时并改为后台生成",
    workspaceUpdated: true,
    sessionUpdated: true,
    agentId: "a1",
  });
  assert.equal(calls.length, 3);
  assert.deepEqual(writes, ["排查标题超时并改为后台生成"]);
  assert.deepEqual(sessionWrites, ["排查标题超时并改为后台生成"]);
});

test("a job without enough time for its steps writes nothing", async () => {
  const clock = makeClock();
  const settings = settingsSchema.parse({});
  const writes = [];
  const { paseo: model } = conversationPaseo(clock, {
    answerFor: (index) => index < 3 ? `第 ${index} 段：排查标题超时` : "排查标题超时并改为后台生成",
  });
  const segments = ["用户：第一段\n\n助手：先看同步时限", "用户：第二段\n\n助手：再看分段预算"];
  const state = {
    workspace: {
      id: "w1",
      projectId: "p1",
      projectDisplayName: "Paseo",
      workspaceDirectory: "/synthetic/workspace",
      name: "synthetic",
      title: "Extend workspace usage plugin",
      background: false,
      metadata: {},
      archivingAt: null,
    },
    agents: [{
      id: "a1",
      workspaceId: "w1",
      title: "Extend workspace usage plugin",
      background: false,
      cwd: "/synthetic/workspace",
      labels: {},
      metadata: {},
    }],
  };
  const paseo = {
    workspaces: {
      ref: () => ({
        refresh: async () => ({ ...state.workspace }),
        setTitle: async (title) => { writes.push(title); state.workspace.title = title; return { title }; },
      }),
    },
    agents: {
      ref: () => ({
        refresh: async () => ({ agent: { ...state.agents[0] } }),
      }),
    },
  };
  const result = await regenerateWorkspaceTitle({
    paseo,
    settings,
    workspaceId: "w1",
    scope: "both",
    claims: new Set(),
    agentClaims: new Set(),
    now: clock.now,
    // Two 5.15 s digests use almost all of this; the synthesis cannot start.
    deadlineAt: clock.now() + 15_000,
    generationTimeoutMs: 35_000,
    listAgents: async () => state.agents,
    readConversation: async () => ({
      text: segments.join("\n\n"),
      turns: 4,
      segments,
      coveredTurns: 4,
      coverage: { kind: "full" },
    }),
    generateConversation: (request, timeoutMs, deadlineAt) =>
      generateConversationTitle(model, settings, request, { timeoutMs, deadlineAt, now: clock.now }),
    renameSession: async () => ({ ok: true }),
  });
  assert.equal(result.status, "error");
  assert.equal(result.reason, "timeout");
  assert.deepEqual(writes, []);
});
