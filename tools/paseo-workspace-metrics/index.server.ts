import { defineSettings } from "@getpaseo/plugin";
import type { PluginServerContext } from "@getpaseo/plugin/server";
import { z } from "zod";
import { cumulativeUsageRpc } from "./shared/cumulative.ts";
import { workspaceScopeRpc } from "./shared/scope.ts";
import { createCumulativeHandler, workspaceScope } from "./server/cumulative.ts";

const settingsSchema = z.object({
  /** Optional daemon-local Codex home. Never supplied by the client. */
  codexHome: z.string().trim().min(1).optional(),
  /** Empty disables cumulative reads; only listed workspaces are served. */
  workspaceIds: z.array(z.string().min(1).max(128)).optional(),
});

export default function contribute(server: PluginServerContext) {
  const settings = server.registerSettings(defineSettings({
    id: "workspace-metrics",
    scope: "host",
    version: 1,
    schema: settingsSchema,
  }));
  server.handle(cumulativeUsageRpc, createCumulativeHandler(settings));
  server.handle(workspaceScopeRpc, async () => workspaceScope(settings));
  return () => {};
}
