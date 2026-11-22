import { defineRpc } from "@getpaseo/plugin";
import { z } from "zod";

/** The daemon-local allowlist. It never returns filesystem paths. */
export const workspaceScopeRpc = defineRpc({
  name: "workspace-metrics.scope",
  input: z.object({}),
  output: z.object({
    workspaceIds: z.array(z.string().min(1).max(128)),
    codexHomeConfigured: z.boolean(),
    error: z.string().nullable(),
  }),
});
