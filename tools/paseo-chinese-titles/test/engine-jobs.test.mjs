import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { promises as fs } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

/**
 * The engine's job wiring, exercised without a daemon: a fake settings store,
 * a fake Paseo API and a synthetic clock. No conversation text, model or
 * credential is involved.
 */
function makeEngineHarness() {
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
      archivedAt: null,
      lastUserMessageAt: "2026-11-24T00:00:00.000Z",
      createdAt: "2026-11-24T00:00:00.000Z",
      updatedAt: "2026-11-24T00:00:00.000Z",
    }],
    workspaceWrites: [],
    sessionWrites: [],
  };
  const settings = {
    read: async () => ({
      status: "ready",
      revision: "r1",
      values: {
        autoNameProjects: false,
        autoNameWorkspaces: false,
        autoNameSessions: false,
        provider: "",
        model: "",
        thinkingOptionId: "",
        projectMaxChars: 20,
        titleMaxChars: 28,
        paseoBin: "paseo",
      },
    }),
    subscribe: () => () => {},
  };
  const paseo = {
    workspaces: {
      ref: (id) => ({
        refresh: async () => (id === state.workspace.id ? { ...state.workspace } : null),
        setTitle: async (title) => {
          state.workspaceWrites.push(title);
          state.workspace.title = title;
          return { title };
        },
        archive: async () => ({}),
      }),
      list: async () => ({ entries: [{ ...state.workspace }] }),
    },
    agents: {
      ref: (id) => ({
        refresh: async () => {
          const agent = state.agents.find((entry) => entry.id === id);
          return agent ? { agent: { ...agent } } : null;
        },
        timeline: {
          // One forward page: a user question and its answer, then the end.
          refetch: async () => ({
            direction: "after",
            projection: "projected",
            hasOlder: false,
            hasNewer: false,
            startCursor: { epoch: "e1", seq: 1 },
            endCursor: { epoch: "e1", seq: 2 },
            entries: [
              { item: { type: "user_message", text: "修一下标题超时" }, turnId: "t1", timestamp: "2026-11-24T00:00:00.000Z", seqStart: 1 },
              { item: { type: "assistant_message", text: "已改为后台任务并加上状态回读" }, turnId: "t1", timestamp: "2026-11-24T00:00:01.000Z", seqStart: 2 },
            ],
            error: null,
          }),
        },
      }),
      list: async () => ({ entries: state.agents.map((agent) => ({ agent: { ...agent } })) }),
    },
    projects: { list: async () => ({ projects: [] }) },
    config: { get: async () => ({ config: { providers: { cchp: { extends: "codex", label: "CCHP" } } } }) },
    providers: {
      snapshot: async () => ({
        entries: [{ provider: "cchp", status: "ready", enabled: true, models: [{ id: "m1", label: "M", isDefault: true }] }],
      }),
      listModels: async () => ({ models: [] }),
    },
  };
  const helperPaseo = {
    ...paseo,
    workspaces: {
      ...paseo.workspaces,
      create: async () => ({
        agents: {
          create: async () => ({
            run: async () => ({ status: "idle", lastMessage: "排查标题超时并改为后台生成" }),
            archive: async () => ({}),
          }),
        },
        archive: async () => ({}),
      }),
    },
  };
  return { state, settings, paseo, helperPaseo };
}

async function settle(engine, jobId) {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    const status = engine.regenerationStatus({ jobId });
    if (status.status !== "running") return status;
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
  return engine.regenerationStatus({ jobId });
}

test("a finished manual job is readable by workspace and by job id, and leaves no in-flight work", async () => {
  const { ChineseTitlesEngine } = await import("../server/engine.ts");
  const { state, settings, paseo, helperPaseo } = makeEngineHarness();
  const engine = new ChineseTitlesEngine(settings);
  try {
    await engine.usePaseo(paseo);
    const started = engine.startRegeneration("w1", helperPaseo, "a1", "workspace");
    assert.equal(started.status, "started");
    // The start call answers synchronously; a second click is refused while the
    // workspace job is registered.
    assert.deepEqual(engine.startRegeneration("w1", helperPaseo, "a1", "workspace"), { status: "busy" });
    const done = await settle(engine, started.jobId);
    assert.equal(done.status, "done");
    assert.equal(done.result.status, "done", JSON.stringify(done.result));
    assert.deepEqual(state.workspaceWrites, ["排查标题超时并改为后台生成"]);
    // The session-only target needs the official CLI, which has no daemon here;
    // a failed CLI write must still be a bounded, explicit partial result.
    const sessionJob = engine.startRegeneration("w1", helperPaseo, "a1", "session");
    assert.equal(sessionJob.status, "started");
    const sessionDone = await settle(engine, sessionJob.jobId);
    assert.equal(sessionDone.status, "done");
    assert.equal(sessionDone.result.status, "error", JSON.stringify(sessionDone.result));
    assert.equal(sessionDone.result.reason, "session_write_failed");
    assert.equal(sessionDone.result.sessionUpdated, false);
    assert.deepEqual(state.sessionWrites, []);
    // The finished job stays readable by id after the next job ran.
    assert.equal(engine.regenerationStatus({ jobId: started.jobId }).status, "done");
  } finally {
    await engine.dispose();
  }
});

test("disposing the engine cancels a running job before its write", async () => {
  const { ChineseTitlesEngine } = await import("../server/engine.ts");
  const { state, settings, paseo } = makeEngineHarness();
  const engine = new ChineseTitlesEngine(settings, {
    renameAgent: async () => ({ ok: false, failure: "should not run" }),
  });
  try {
    await engine.usePaseo(paseo);
    // A slow conversation read keeps the job in flight while the engine stops.
    const slowPaseo = {
      ...paseo,
      workspaces: {
        ...paseo.workspaces,
        ref: () => ({
          refresh: async () => ({ ...state.workspace }),
          setTitle: async (title) => {
            state.workspaceWrites.push(title);
            state.workspace.title = title;
            return { title };
          },
        }),
      },
    };
    const started = engine.startRegeneration("w1", slowPaseo, "a1", "workspace");
    assert.equal(started.status, "started");
    await engine.dispose();
    assert.deepEqual(engine.regenerationStatus({ jobId: started.jobId }), { status: "unknown" });
    assert.deepEqual(state.workspaceWrites, []);
  } finally {
    await engine.dispose();
  }
});

test("a failing state save names the save step and keeps the selected session", async (t) => {
  const { ChineseTitlesEngine } = await import("../server/engine.ts");
  const { state, settings, paseo, helperPaseo } = makeEngineHarness();
  const root = await fs.mkdtemp(join(tmpdir(), "chinese-titles-state-"));
  const previous = { HOME: process.env.HOME, PASEO_HOME: process.env.PASEO_HOME };
  // The state file path is occupied by a non-empty directory, so the final
  // rename of the bookkeeping write fails after the title itself was written
  // and verified. Nothing else about the run is disturbed.
  const paseoHome = join(root, "paseo-home");
  const namespace = createHash("sha256").update(paseoHome).digest("hex").slice(0, 32);
  const dataDir = join(root, ".paseo", "plugin-data", "paseo-chinese-titles", "daemons", namespace);
  await fs.mkdir(join(dataDir, "state.json"), { recursive: true });
  await fs.writeFile(join(dataDir, "state.json", "occupied"), "x");
  const warn = t.mock.method(console, "warn", () => {});
  process.env.HOME = root;
  process.env.PASEO_HOME = paseoHome;
  const engine = new ChineseTitlesEngine(settings);
  try {
    await engine.usePaseo(paseo);
    const started = engine.startRegeneration("w1", helperPaseo, "a1", "workspace");
    assert.equal(started.status, "started");
    const done = await settle(engine, started.jobId);
    // The run itself succeeded and wrote the title; only the save threw.
    assert.equal(done.status, "done");
    assert.equal(done.result.status, "error", JSON.stringify(done.result));
    assert.equal(done.result.reason, "internal_failed");
    assert.deepEqual(state.workspaceWrites, ["排查标题超时并改为后台生成"]);
    assert.equal(warn.mock.callCount(), 1);
    const args = warn.mock.calls[0].arguments;
    assert.equal(args.length, 1, "one argument, so the line stays searchable");
    const prefix = "[paseo-chinese-titles] regeneration job failed ";
    assert.equal(args[0].startsWith(prefix), true);
    const line = JSON.parse(args[0].slice(prefix.length));
    assert.equal(line.stage, "state_save", "the step that actually failed");
    assert.equal(line.agentId, "a1", "the selection survives the save failure");
    assert.equal("budgetMs" in line, false, "no model budget left over on the save step");
    assert.equal("timeoutSource" in line, false, "no clock reported for the save step");
    assert.equal(JSON.stringify(line).includes("排查标题超时并改为后台生成"), false, "no title text");
  } finally {
    await engine.dispose();
    if (previous.HOME === undefined) delete process.env.HOME; else process.env.HOME = previous.HOME;
    if (previous.PASEO_HOME === undefined) delete process.env.PASEO_HOME; else process.env.PASEO_HOME = previous.PASEO_HOME;
    await fs.rm(root, { recursive: true, force: true });
  }
});
