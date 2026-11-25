/** Filesystem reads for the daemon-side sampler. Server bundle only. */

import os from "node:os";
import { execFile } from "node:child_process";
import { readFile, statfs } from "node:fs/promises";
import {
  dfPercent,
  localMounts,
  parseLoadAverage,
  parseMeminfo,
  parseMeminfoDetail,
  parseProcNetDev,
  parseProcStat,
  parseProcStatCpu,
  parseUptime,
  parseVmRss,
  parseVmStat,
  parseMemoryPressure,
  type CpuTimes,
  type NetTotals,
} from "../shared/aggregate.ts";

export async function readProcStatCpu(): Promise<CpuTimes | null> {
  return parseProcStatCpu(await readFile("/proc/stat", "utf8"));
}

export async function readMemory(): Promise<{ totalBytes: number; availableBytes: number | null } | null> {
  return parseMeminfo(await readFile("/proc/meminfo", "utf8"));
}

/** Cached/buffers split of /proc/meminfo; optional, never blocks the main reading. */
export async function readMemoryDetail(): Promise<{ cachedBytes: number; buffersBytes: number } | null> {
  return parseMeminfoDetail(await readFile("/proc/meminfo", "utf8"));
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

/**
 * Linux reads the kernel's own 1/5/15 figures. Darwin gets them from
 * os.loadavg(), which is a real kernel value there. Windows has no equivalent,
 * so it stays null instead of a fabricated 0.
 */
export async function readLoadAverage(): Promise<{ one: number; five: number; fifteen: number } | null> {
  if (process.platform === "linux") {
    return parseLoadAverage(await readFile("/proc/loadavg", "utf8"));
  }
  if (process.platform === "darwin") {
    const [one, five, fifteen] = os.loadavg();
    return [one, five, fifteen].every((value) => Number.isFinite(value) && value >= 0) ? { one, five, fifteen } : null;
  }
  return null;
}

/** Uptime in seconds: /proc/uptime on Linux, os.uptime() on Darwin and Windows. */
export async function readUptime(): Promise<number | null> {
  if (process.platform === "linux") {
    return parseUptime(await readFile("/proc/uptime", "utf8"));
  }
  if (process.platform === "darwin" || process.platform === "win32") {
    const seconds = os.uptime();
    return Number.isFinite(seconds) && seconds >= 0 ? seconds : null;
  }
  return null;
}

export interface DiskEntry {
  mountPoint: string;
  source: string;
  fstype: string;
  totalBytes: number;
  usedBytes: number;
  availableBytes: number;
  percent: number | null;
}

/**
 * Every local disk of the daemon host, one entry per device, in df terms.
 * Unreadable mounts are skipped; a failure here returns null and leaves the
 * root reading in the rest of the payload untouched.
 */
export async function readLocalDisks(): Promise<DiskEntry[] | null> {
  if (process.platform !== "linux") return null;
  const text = await readFile("/proc/mounts", "utf8").catch(() => null);
  if (text === null) return null;
  const entries: DiskEntry[] = [];
  for (const mount of localMounts(text)) {
    const stats = await statfs(mount.mountPoint).catch(() => null);
    if (!stats) continue;
    const bsize = Number(stats.bsize);
    const blocks = Number(stats.blocks);
    const bfree = Number(stats.bfree);
    const bavail = Number(stats.bavail);
    if (!(bsize > 0) || !(blocks > 0)) continue;
    const totalBytes = blocks * bsize;
    const usedBytes = Math.max(0, (blocks - bfree) * bsize);
    const availableBytes = Math.max(0, bavail * bsize);
    entries.push({
      mountPoint: mount.mountPoint,
      source: mount.source,
      fstype: mount.fstype,
      totalBytes,
      usedBytes,
      availableBytes,
      percent: dfPercent(usedBytes, availableBytes),
    });
  }
  return entries;
}

/** macOS only: Activity Monitor style memory via the two documented binaries. */
const MAC_VM_STAT = "/usr/bin/vm_stat";
const MAC_SYSCTL = "/usr/sbin/sysctl";

function runMac(binary: string, args: string[]): Promise<string | null> {
  return new Promise((resolve) => {
    execFile(binary, args, { timeout: 2_000, maxBuffer: 64 * 1024 }, (error, stdout) => {
      resolve(error ? null : String(stdout));
    });
  });
}

export async function readMacMemory(): Promise<{
  appBytes: number | null;
  wiredBytes: number | null;
  compressedBytes: number | null;
  cachedBytes: number | null;
  usedBytes: number | null;
  pressure: "normal" | "warning" | "critical" | null;
} | null> {
  if (process.platform !== "darwin") return null;
  const [vmText, pressureText] = await Promise.all([
    runMac(MAC_VM_STAT, []),
    runMac(MAC_SYSCTL, ["-n", "kern.memorystatus_vm_pressure_level"]),
  ]);
  if (vmText === null) return null;
  // vm_stat prints "page size of 16384 bytes".
  const sizeMatch = /page size of (\d+) bytes/.exec(vmText);
  const pageSize = sizeMatch ? Number(sizeMatch[1]) : 4096;
  const memory = parseVmStat(vmText, pageSize);
  if (!memory) return null;
  return { ...memory, pressure: pressureText ? parseMemoryPressure(pressureText) : null };
}
