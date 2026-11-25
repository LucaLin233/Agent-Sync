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
    /**
     * Host-wide network rates from /proc/net/dev. Null when the platform has no
     * counter or the previous baseline is not comparable; a zero rate is a real
     * measurement and is reported as 0.
     */
    network: z
      .object({
        rxBytesPerSecond: z.number().nonnegative().nullable(),
        txBytesPerSecond: z.number().nonnegative().nullable(),
        windowMs: z.number().int().nonnegative(),
      })
      .nullable(),
    /** Seconds since the host booted; null where the platform has no counter. */
    uptimeSeconds: z.number().nonnegative().nullable(),
    /** 1/5/15 minute host load average; null where unavailable. */
    loadAverage: z
      .object({ one: z.number().nonnegative(), five: z.number().nonnegative(), fifteen: z.number().nonnegative() })
      .nullable(),
    /**
     * Local disks, one row per device, df semantics. Null when enumeration is
     * unsupported or failed; `disk` still carries the system root.
     */
    disks: z
      .array(
        z.object({
          mountPoint: z.string(),
          source: z.string(),
          fstype: z.string(),
          totalBytes: z.number().nonnegative(),
          usedBytes: z.number().nonnegative(),
          availableBytes: z.number().nonnegative(),
          percent: z.number().min(0).max(100).nullable(),
        }),
      )
      .nullable(),
    /** "local-mounts" = enumerated; "root-only" = fallback to the root reading. */
    diskScope: z.enum(["local-mounts", "root-only"]),
    /** Reclaimable page cache and buffers, when the platform reports them. */
    memoryBreakdown: z
      .object({ cachedBytes: z.number().nonnegative().nullable(), buffersBytes: z.number().nonnegative().nullable() })
      .nullable(),
    /** macOS kernel pressure level; null on platforms without the concept. */
    memoryPressure: z.enum(["normal", "warning", "critical"]).nullable(),
    /** Bounded in-memory history, oldest first. Disks are not repeated here. */
    history: z.object({
      intervalMs: z.number().int().positive(),
      /** Oldest first; kept to about three minutes. */
      samples: z.array(
        z.object({
          at: z.string(),
          cpuPercent: z.number().min(0).max(100).nullable(),
          memoryPercent: z.number().min(0).max(100).nullable(),
          rxBytesPerSecond: z.number().nonnegative().nullable(),
          txBytesPerSecond: z.number().nonnegative().nullable(),
        }),
      ),
    }),
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
