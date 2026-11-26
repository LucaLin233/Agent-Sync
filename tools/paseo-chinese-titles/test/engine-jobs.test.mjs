import test from "node:test";
import assert from "node:assert/strict";

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
