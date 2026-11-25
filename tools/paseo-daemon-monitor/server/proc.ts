/** Filesystem reads for the daemon-side sampler. Server bundle only. */

import { statfs } from "node:fs/promises";
import { readFile } from "node:fs/promises";
import { parseMeminfo, parseProcNetDev, parseProcStat, parseProcStatCpu, parseVmRss, type CpuTimes, type NetTotals } from "../shared/aggregate.ts";

export async function readProcStatCpu(): Promise<CpuTimes | null> {
  return parseProcStatCpu(await readFile("/proc/stat", "utf8"));
}

export async function readMemory(): Promise<{ totalBytes: number; availableBytes: number | null } | null> {
  return parseMeminfo(await readFile("/proc/meminfo", "utf8"));
}

export async function readProcess(pid: number): Promise<{ pid: number; ticks: number; startTicks: number; rssBytes: number | null } | null> {
  const [statText, statusText] = await Promise.all([
    readFile(`/proc/${pid}/stat`, "utf8"),
    readFile(`/proc/${pid}/status`, "utf8").catch(() => ""),
  ]);
  const stat = parseProcStat(statText);
  if (!stat) return null;
  return { pid, ...stat, rssBytes: parseVmRss(statusText) };
}

/** The filesystem that holds the platform's system root. No path crosses the wire. */
export async function readSystemDisk() {
  const stats = await statfs(process.platform === "win32" ? "C:\\" : "/");
  return { blocks: stats.blocks, bfree: stats.bfree, bavail: stats.bavail, bsize: stats.bsize };
}

/** Aggregate rx/tx counters of physical interfaces. Linux only; no traffic generated. */
export async function readNetDev(): Promise<NetTotals | null> {
  if (process.platform !== "linux") return null;
  return parseProcNetDev(await readFile("/proc/net/dev", "utf8"));
}
