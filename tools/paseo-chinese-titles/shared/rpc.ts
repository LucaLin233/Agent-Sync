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

/**
 * Where the one generated summary is written. The panel sends "both"; an old
 * client that omits the field keeps the previous workspace-only behaviour.
 */
export const regenerateScopeSchema = z.enum(["both", "workspace", "session"]);

export const regenerateWorkspaceTitleRpc = defineRpc({
  name: "chinese-titles.regenerate-workspace",
  input: z.object({
    workspaceId: z.string().trim().min(1).max(200),
    /** The session the user picked; omitted only when the workspace has exactly one eligible session. */
    agentId: z.string().trim().min(1).max(200).optional(),
    scope: regenerateScopeSchema.optional(),
  }),
  output: z.object({
    status: z.enum(["done", "partial", "busy", "needs_selection", "skipped", "error"]),
    title: z.string().optional(),
    reason: z.string().optional(),
    /** Each write is independent; the two flags say exactly what was written. */
    workspaceUpdated: z.boolean(),
    sessionUpdated: z.boolean(),
    /**
     * Present only when some readable turns were not covered (page/entry/char
     * limit, a timeline reset or gap, a read error or the segment budget). The
     * title then describes the covered part, not the whole session.
     */
    coverage: z.object({
      kind: z.literal("partial"),
      reason: z.string().optional(),
      turns: z.number().int().nonnegative(),
    }).optional(),
  }),
});
