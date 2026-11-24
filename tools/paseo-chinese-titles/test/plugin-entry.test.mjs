import test from "node:test";
import assert from "node:assert/strict";
import { register } from "node:module";
import { createHash } from "node:crypto";
import { promises as fs } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { settingsSchema } from "../shared/settings.ts";

// The daemon bundles this plugin, so its sources import "../../shared/rpc"
// without an extension. Node's type stripping needs the extension, so register
// a tiny resolve hook for this test only.
const HOOK_SOURCE = `
export async function resolve(specifier, context, next) {
  try {
    return await next(specifier, context);
  } catch (error) {
    if (specifier.startsWith(".") && !/\\.[cm]?[jt]sx?$/.test(specifier)) {
      return next(specifier + ".ts", context);
    }
    throw error;
  }
}
`;
register(`data:text/javascript,${encodeURIComponent(HOOK_SOURCE)}`);

// The real entry point: contribute() registers the hooks the daemon calls.
// HOME/PASEO_HOME point at a private temp root so the plugin state never
// touches the live daemon.
async function withSandbox(run) {
  const root = await fs.mkdtemp(join(tmpdir(), "chinese-titles-entry-"));
  const previous = { HOME: process.env.HOME, PASEO_HOME: process.env.PASEO_HOME, PATH: process.env.PATH };
  process.env.HOME = root;
  process.env.PASEO_HOME = join(root, "paseo-home");
  // The completed-turn path attempts the official CLI rename; with no `paseo`
  // on PATH that fails as `cli_missing` instead of spawning a real daemon call.
  process.env.PATH = "/nonexistent-for-plugin-entry-test";
  try {
    return await run(root);
  } finally {
    for (const key of ["HOME", "PASEO_HOME", "PATH"]) {
      if (previous[key] === undefined) delete process.env[key];
      else process.env[key] = previous[key];
    }
    await fs.rm(root, { recursive: true, force: true });
  }
}

function makeTimeline(turns) {
  const entries = [];
  for (const turn of turns) {
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
  return {
    config: { get: async () => ({ config: { providers: { cchp: { extends: "codex", label: "CCHP" } } } }) },
    providers: {
      snapshot: async () => ({ entries: [{
        provider: "cchp", status: "ready", enabled: true, models: [{ id: "m1", label: "M", isDefault: true }],
      }] }),
      listModels: async () => ({ models: [] }),
    },
    projects: { list: async () => ({ projects: [] }) },
    workspaces: {
      list: async () => ({ entries: [{ ...state.workspace }] }),
      ref: () => ({
        refresh: async () => ({ ...state.workspace }),
        setTitle: async (title) => { state.workspace.title = title; return { title }; },
      }),
      create: async () => ({
        agents: {
          create: async () => ({
            run: async () => {
              state.modelCalls += 1;
              return { status: "idle", lastMessage: state.modelAnswer };
            },
            archive: async () => ({}),
          }),
        },
        archive: async () => ({}),
      }),
    },
    agents: {
      list: async () => ({ entries: [{ agent: { ...state.agent } }], pageInfo: { hasMore: false } }),
      ref: () => ({
        refresh: async () => ({ agent: { ...state.agent } }),
        timeline: makeTimeline(state.turns),
      }),
    },
  };
}

async function seedState(root, agentEntry) {
  const dir = join(root, ".paseo", "plugin-data", "paseo-chinese-titles", "daemons",
    createHash("sha256").update(join(root, "paseo-home")).digest("hex").slice(0, 32));
  await fs.mkdir(dir, { recursive: true, mode: 0o700 });
  await fs.writeFile(join(dir, "state.json"), JSON.stringify({
    version: 1,
    initialized: true,
    installedAt: "2026-11-24T00:00:00.000Z",
    projects: {},
    workspaces: { w1: { status: "done", at: "2026-11-24T00:00:00.000Z", title: "已命名的工作区" } },
    agents: { a1: agentEntry },
  }), { encoding: "utf8", mode: 0o600 });
}

async function contributed(root, state) {
  // Persist before the engine is constructed: it loads state once on startup.
  if (state.persist) await seedState(root, state.persist);
  const { default: contribute } = await import("../server/plugin.ts");
  const hooks = new Map();
  const rpcs = [];
  const settings = {
    read: async () => ({ status: "ready", revision: "1", values: settingsSchema.parse({ autoNameSessions: true }) }),
    subscribe: () => () => undefined,
  };
  const server = {
    registerSettings: () => settings,
    addHook: (name, handler) => { hooks.set(name, handler); return () => undefined; },
    handle: (contract, handler) => { rpcs.push({ name: contract.name, handler }); },
    registerProvider: () => undefined,
    registerUsageSource: () => undefined,
    registerWorktreeManager: () => () => undefined,
  };
  const cleanup = contribute(server);
  const paseo = makePaseo(state);
  return { hooks, rpcs, paseo, cleanup, root };
}

function agentStatePath(root) {
  const namespace = createHash("sha256").update(join(root, "paseo-home")).digest("hex").slice(0, 32);
  return join(root, ".paseo", "plugin-data", "paseo-chinese-titles", "daemons", namespace, "state.json");
}

async function readAgentState(root) {
  const raw = await fs.readFile(agentStatePath(root), "utf8").catch(() => null);
  return raw ? JSON.parse(raw).agents?.a1 ?? {} : {};
}

function initialState() {
  return {
    workspace: {
      id: "w1", projectId: "p1", projectDisplayName: "Paseo",
      workspaceDirectory: "/synthetic/workspace", name: "w1", title: "已命名的工作区",
      background: false, metadata: {}, archivingAt: null,
    },
    agent: {
      id: "a1", workspaceId: "w1", title: "先看 Codex 为什么走 WebSocket",
      background: false, cwd: "/synthetic/workspace", labels: {}, metadata: {},
      lastUserMessageAt: "2026-11-24T00:00:00.000Z",
      createdAt: "2026-11-24T00:00:00.000Z", updatedAt: "2026-11-24T00:00:00.000Z",
    },
    turns: [{ id: "t1", question: "先看 Codex 为什么走 WebSocket", answer: "Codex 与 daemon 之间是 WebSocket 长连接。" }],
    modelAnswer: "排查 Codex 长连接原因",
    modelCalls: 0,
  };
}

test("the plugin registers the official turn hooks and RPCs", async () => {
  await withSandbox(async (root) => {
    const { hooks, rpcs, cleanup } = await contributed(root, initialState());
    try {
      for (const name of [
        "workspace.create.before",
        "workspace.create.after",
        "agent.create.after",
        "agent.turn.before",
        "agent.turn.after",
      ]) {
        assert.equal(typeof hooks.get(name), "function", `${name} must be registered`);
      }
      assert.ok(rpcs.some((entry) => entry.name === "chinese-titles.regenerate-workspace"));
    } finally {
      cleanup();
    }
  });
});

test("a failed or canceled turn through the real hook spends no naming attempt", async () => {
  await withSandbox(async (root) => {
    const state = initialState();
    const { hooks, paseo, cleanup } = await contributed(root, state);
    try {
      for (const outcome of [{ kind: "failed", error: { message: "boom" } }, { kind: "canceled", reason: "user" }]) {
        await hooks.get("agent.turn.after")({ agent: { id: "a1" }, turnId: "t1", outcome }, { paseo });
      }
      assert.equal(state.modelCalls, 0, "no model call for an unfinished turn");
      const saved = await readAgentState(root);
      assert.equal(saved.attempts, undefined);
      assert.equal(saved.status, "pending");
    } finally {
      cleanup();
    }
  });
});

test("a completed turn through the real hook reaches the model and records the attempt", async () => {
  await withSandbox(async (root) => {
    const state = initialState();
    const { hooks, paseo, cleanup } = await contributed(root, state);
    try {
      await hooks.get("agent.turn.after")(
        { agent: { id: "a1" }, turnId: "t1", outcome: { kind: "completed" } },
        { paseo },
      );
      assert.equal(state.modelCalls, 1, "the completed turn is naming material");
      const saved = await readAgentState(root);
      assert.equal(saved.lastTurnId, "t1");
      assert.equal(saved.attempts, 1);
      // The CLI rename cannot run in the test sandbox; the attempt is still
      // recorded and the provisional title is untouched.
      assert.notEqual(saved.status, "done");
      assert.equal(state.agent.title, "先看 Codex 为什么走 WebSocket");
    } finally {
      cleanup();
    }
  });
});

test("after a session is named, later turns do no reads and no model calls", async () => {
  await withSandbox(async (root) => {
    const state = initialState();
    // A completed, named session: the state records the title it wrote.
    state.agent.title = "排查 Codex 长连接原因";
    state.persist = {
      status: "done", at: "2026-11-24T00:00:00.000Z", title: "排查 Codex 长连接原因",
      attempts: 1, lastTurnId: "t1", workspaceId: "w1",
    };
    const { hooks, paseo, cleanup } = await contributed(root, state);
    try {
      let reads = 0;
      const originalRef = paseo.agents.ref;
      paseo.agents.ref = (id) => {
        const handle = originalRef(id);
        return {
          ...handle,
          refresh: async () => { reads += 1; return handle.refresh(); },
        };
      };
      await hooks.get("agent.turn.after")(
        { agent: { id: "a1" }, turnId: "t2", outcome: { kind: "completed" } },
        { paseo },
      );
      assert.equal(reads, 0, "a finished session causes no agent refresh");
      assert.equal(state.modelCalls, 0, "and no model call");
      assert.equal(state.agent.title, "排查 Codex 长连接原因");
    } finally {
      cleanup();
    }
  });
});
