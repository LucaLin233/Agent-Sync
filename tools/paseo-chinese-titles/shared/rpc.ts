import { defineRpc } from "@getpaseo/plugin";
import { z } from "zod";

export const reconcileRpc = defineRpc({
  name: "chinese-titles.reconcile",
  input: z.object({}),
  output: z.object({
    ok: z.boolean(),
    projects: z.number().int().nonnegative(),
    workspaces: z.number().int().nonnegative(),
    agents: z.number().int().nonnegative(),
  }),
});

export const titleCatalogRpc = defineRpc({
  name: "chinese-titles.provider-catalog",
  input: z.object({}),
  output: z.object({
    providers: z.array(z.object({
      id: z.string(),
      label: z.string(),
      models: z.array(z.object({
        id: z.string(),
        label: z.string(),
        isDefault: z.boolean(),
        defaultThinkingOptionId: z.string().optional(),
        thinkingOptions: z.array(z.object({
          id: z.string(),
          label: z.string(),
          isDefault: z.boolean(),
        })),
      })),
    })),
  }),
});

export const listWorkspaceSessionsRpc = defineRpc({
  name: "chinese-titles.workspace-sessions",
  input: z.object({
    workspaceId: z.string().trim().min(1).max(200),
  }),
  output: z.object({
    sessions: z.array(z.object({
      id: z.string(),
      title: z.string().nullable(),
      lastActivityAt: z.string().nullable(),
    })),
  }),
});

export const regenerateWorkspaceTitleRpc = defineRpc({
  name: "chinese-titles.regenerate-workspace",
  input: z.object({
    workspaceId: z.string().trim().min(1).max(200),
    /** The session the user picked; omitted only when the workspace has exactly one eligible session. */
    agentId: z.string().trim().min(1).max(200).optional(),
  }),
  output: z.object({
    status: z.enum(["done", "busy", "needs_selection", "skipped", "error"]),
    title: z.string().optional(),
    reason: z.string().optional(),
  }),
});
