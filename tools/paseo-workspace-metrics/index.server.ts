import type { PluginServerContext } from "@getpaseo/plugin/server";
import { cumulativeUsageRpc, turnOutputRpc } from "./shared/cumulative.ts";
import { metricsSettings } from "./shared/settings.ts";
import { workspaceScopeRpc, workspaceSettingsSubscription } from "./shared/scope.ts";
import {
  createCumulativeHandler,
  createScopeSubscriptionHandler,
  createTurnOutputHandler,
  workspaceScope,
} from "./server/cumulative.ts";

export default function contribute(server: PluginServerContext) {
  const settings = server.registerSettings(metricsSettings);
  server.handle(cumulativeUsageRpc, createCumulativeHandler(settings));
  server.handle(turnOutputRpc, createTurnOutputHandler(settings));
  server.handle(workspaceScopeRpc, async () => workspaceScope(settings));
  server.handle(workspaceSettingsSubscription, createScopeSubscriptionHandler(settings));
  return () => {};
}
