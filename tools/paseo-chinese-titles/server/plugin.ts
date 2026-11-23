import type { PluginServerContext } from "@getpaseo/plugin/server";
import { reconcileRpc, regenerateWorkspaceTitleRpc, titleCatalogRpc } from "../shared/rpc";
import { listTitleProviderOptions } from "./provider";
import { CHINESE_TITLES_SETTINGS } from "../shared/settings";
import { listAgentIdsViaCli, listProjectIdsViaCli, listWorkspaceIdsViaCli } from "./cli";
import { ChineseTitlesEngine } from "./engine";

export default function contribute(server: PluginServerContext) {
  const settings = server.registerSettings(CHINESE_TITLES_SETTINGS);
  const engine = new ChineseTitlesEngine(settings);
  engine.startCliPolling();

  // The server contribution has no PaseoApi at load. Baseline through the
  // official CLI when possible; otherwise the first hook/RPC does it.
  void (async () => {
    const current = await settings.read();
    if (current.status !== "ready") return;
    const [projects, workspaces, agents] = await Promise.all([
      listProjectIdsViaCli(current.values),
      listWorkspaceIdsViaCli(current.values),
      listAgentIdsViaCli(current.values),
    ]);
    if (projects && workspaces && agents) {
      await engine.initializeFromCli(projects, workspaces, agents);
    }
  })().catch(() => undefined);

  server.addHook("workspace.create.before", async ({ request }) => {
    const seed = await engine.workspaceTitleSeed(request);
    if (!seed) return;
    return { ...request, title: seed.title, metadata: seed.metadata };
  });
  server.addHook("workspace.create.after", async ({ workspace }, context) => {
    await engine.onWorkspaceCreated(workspace, context.paseo);
  });
  server.addHook("agent.create.after", async ({ agent }, context) => {
    await engine.usePaseo(context.paseo);
    await engine.onAgentCreated(agent.id, context.paseo);
  });
  server.addHook("agent.turn.before", async ({ agent, turnId }, context) => {
    await engine.onTurn(agent.id, turnId, context.paseo);
  });
  server.addHook("agent.turn.after", async ({ agent }, context) => {
    await engine.onTurn(agent.id, null, context.paseo);
  });
  server.handle(reconcileRpc, async (_input, { paseo }) => engine.reconcile(paseo));
  server.handle(regenerateWorkspaceTitleRpc, async ({ workspaceId }, { paseo }) =>
    engine.regenerateWorkspaceTitle(workspaceId, paseo));
  server.handle(titleCatalogRpc, async (_input, { paseo }) => listTitleProviderOptions(paseo));

  return () => {
    void engine.dispose();
  };
}
