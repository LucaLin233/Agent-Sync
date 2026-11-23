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
