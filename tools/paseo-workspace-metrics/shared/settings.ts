import { defineSettings } from "@getpaseo/plugin";
import { z } from "zod";

/** Host settings shared by the daemon handler and the settings screen. */
export const metricsSettings = defineSettings({
  id: "workspace-metrics",
  scope: "host",
  version: 1,
  schema: z.object({
    /** Optional daemon-local Codex home. Empty means auto-discover. */
    codexHome: z.string().trim().min(1).optional(),
    /** Optional daemon-local Claude config dir (CLAUDE_CONFIG_DIR). Empty means auto-discover. */
    claudeHome: z.string().trim().min(1).optional(),
    /** Explicit cumulative switch. Missing documents fall back to the legacy allowlist. */
    cumulativeEnabled: z.boolean().optional(),
    /** Legacy unrestricted switch kept for saved documents and the advanced UI. */
    allWorkspaces: z.boolean().optional(),
    /** Empty means unrestricted only when allWorkspaces is true. */
    workspaceIds: z.array(z.string().min(1).max(128)).optional(),
  }),
});
