import { defineRpc } from "@getpaseo/plugin";
import { z } from "zod";

/**
 * One reading of the host that runs this plugin's daemon. The client sends no
 * path, command or host identifier: the installation is bound to one daemon.
 */
export const hostResourcesRpc = defineRpc({
  name: "host-resources.sample",
  input: z.object({}),
  output: z.object({
    sampledAt: z.string(),
    platform: z.string(),
    cpuCores: z.number().int().positive(),
    /** Which counter produced the CPU delta; "proc" (Linux) or "os". */
    cpuSource: z.enum(["proc", "os"]),
    cpuPercent: z.number().min(0).max(100).nullable(),
    cpuWindowMs: z.number().int().nonnegative(),
    memoryPercent: z.number().min(0).max(100).nullable(),
    memoryUsedBytes: z.number().nonnegative().nullable(),
    memoryTotalBytes: z.number().nonnegative(),
    /** "available" = MemAvailable on Linux; "free" = os.freemem() elsewhere. */
    memoryBasis: z.enum(["available", "free"]),
    /** Capacity of the filesystem holding the system root; null when statfs failed. */
    disk: z
      .object({
        totalBytes: z.number().nonnegative(),
        usedBytes: z.number().nonnegative(),
        availableBytes: z.number().nonnegative(),
        percent: z.number().min(0).max(100).nullable(),
      })
      .nullable(),
    /** Present only when the daemon parent process is verifiable through /proc. */
    process: z
      .object({
        pid: z.number().int().positive(),
        /** Daemon CPU over all host cores; null until two readings exist. */
        cpuPercent: z.number().min(0).nullable(),
        rssBytes: z.number().nonnegative().nullable(),
      })
      .nullable(),
  }),
});

export type HostResources = z.infer<typeof hostResourcesRpc.output>;
