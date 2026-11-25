import os from "node:os";
import type { PluginHandlerContext } from "@getpaseo/plugin/server";
import {
  cpuUsagePercent,
  diskUsage,
  memoryUsagePercent,
  processCpuPercent,
  readCpuTimes,
  type CpuTimes,
} from "../shared/aggregate.ts";
import type { HostResources } from "../shared/contract.ts";
import { readMemory, readProcStatCpu, readProcess, readSystemDisk } from "./proc.ts";

const CACHE_MS = 1_000;
const PRIME_MS = 250;

/** The forked plugin worker's parent is the daemon; pin it once, never re-derive it. */
const DAEMON_PID = process.ppid > 0 ? process.ppid : null;

interface CpuBaseline {
  source: "proc" | "os";
  times: CpuTimes;
  at: number;
  /** Present only for a /proc baseline, where process ticks share the same counter. */
  process: ProcessBaseline | null;
}

interface ProcessBaseline {
  pid: number;
  startTicks: number;
  ticks: number;
}

let baseline: CpuBaseline | null = null;
let cached: { at: number; value: HostResources } | null = null;
let inflight: Promise<HostResources> | null = null;

async function readCpu(): Promise<{ source: "proc" | "os"; times: CpuTimes } | null> {
  if (process.platform === "linux") {
    const proc = await readProcStatCpu().catch(() => null);
    if (proc) return { source: "proc", times: proc };
  }
  const cpus = os.cpus();
  return cpus.length > 0 ? { source: "os", times: readCpuTimes(cpus) } : null;
}

/**
 * Only a live IPC child whose parent still matches the pinned daemon PID is
 * sampled; reparenting or a detached channel would otherwise report a stranger.
 */
async function readDaemonProcess(): Promise<{ pid: number; ticks: number; startTicks: number; rssBytes: number | null } | null> {
  if (process.platform !== "linux" || DAEMON_PID === null) return null;
  if (!process.connected || process.ppid !== DAEMON_PID) return null;
  return readProcess(DAEMON_PID).catch(() => null);
}

async function readMemorySnapshot(): Promise<{ totalBytes: number; availableBytes: number | null; basis: "available" | "free" }> {
  if (process.platform === "linux") {
    const memory = await readMemory().catch(() => null);
    if (memory) return { ...memory, basis: "available" };
  }
  return { totalBytes: os.totalmem(), availableBytes: os.freemem(), basis: "free" };
}

function buildValue(input: {
  previous: CpuBaseline | null;
  cpu: { source: "proc" | "os"; times: CpuTimes } | null;
  process: Awaited<ReturnType<typeof readDaemonProcess>>;
  memory: { totalBytes: number; availableBytes: number | null; basis: "available" | "free" };
  disk: Awaited<ReturnType<typeof readSystemDisk>> | null;
}): HostResources {
  const { previous, cpu, process: daemon, memory, disk } = input;
  // A delta is only meaningful between two readings of the same counter.
  const comparable = previous !== null && cpu !== null && previous.source === cpu.source;
  const hostTicks = comparable ? cpu.times.total - previous.times.total : 0;
  const memoryUsedBytes = memory.availableBytes === null ? null : Math.max(0, memory.totalBytes - memory.availableBytes);
  const diskUse = disk ? diskUsage(disk) : null;

  let processValue: HostResources["process"] = null;
  if (daemon) {
    const prior = previous?.process ?? null;
    // A different PID or start time means the daemon restarted; the old base is void.
    const same = prior !== null && prior.pid === daemon.pid && prior.startTicks === daemon.startTicks;
    processValue = {
      pid: daemon.pid,
      // Process ticks and host ticks must both come from /proc to share USER_HZ.
      cpuPercent:
        same && previous?.source === "proc" && cpu?.source === "proc"
          ? processCpuPercent(prior.ticks, daemon.ticks, hostTicks)
          : null,
      rssBytes: daemon.rssBytes,
    };
  }

  return {
    sampledAt: new Date().toISOString(),
    platform: process.platform,
    cpuCores: os.cpus().length,
    cpuSource: cpu?.source ?? "os",
    cpuPercent: comparable ? cpuUsagePercent(previous.times, cpu.times) : null,
    cpuWindowMs: comparable ? Math.max(0, Date.now() - previous.at) : 0,
    memoryPercent: memoryUsagePercent(memory.totalBytes, memory.availableBytes),
    memoryUsedBytes,
    memoryTotalBytes: memory.totalBytes,
    memoryBasis: memory.basis,
    disk: diskUse
      ? {
          totalBytes: diskUse.totalBytes,
          usedBytes: diskUse.usedBytes,
          availableBytes: diskUse.availableBytes,
          percent: diskUse.percent,
        }
      : null,
    process: processValue,
  };
}

async function sample(): Promise<HostResources> {
  const startedAt = Date.now();
  const firstCpu = await readCpu();
  const firstProcess = await readDaemonProcess();
  const memory = await readMemorySnapshot();
  const disk = await readSystemDisk().catch(() => null);

  // Without an earlier reading there is no delta to report. Take a second reading
  // inside this call so a freshly started daemon never shows a fabricated 0%.
  if (!baseline && firstCpu) {
    await new Promise((resolve) => setTimeout(resolve, PRIME_MS));
    const secondCpu = await readCpu();
    const secondProcess = await readDaemonProcess();
    const primed: CpuBaseline = {
      source: firstCpu.source,
      times: firstCpu.times,
      at: startedAt,
      process: firstProcess
        ? { pid: firstProcess.pid, startTicks: firstProcess.startTicks, ticks: firstProcess.ticks }
        : null,
    };
    const value = buildValue({ previous: primed, cpu: secondCpu, process: secondProcess, memory, disk });
    const stored = secondCpu ?? firstCpu;
    baseline = {
      source: stored.source,
      times: stored.times,
      at: Date.now(),
      process: secondProcess
        ? { pid: secondProcess.pid, startTicks: secondProcess.startTicks, ticks: secondProcess.ticks }
        : null,
    };
    return value;
  }

  const previous = baseline;
  const value = buildValue({ previous, cpu: firstCpu, process: firstProcess, memory, disk });
  if (firstCpu) {
    baseline = {
      source: firstCpu.source,
      times: firstCpu.times,
      at: Date.now(),
      process: firstProcess
        ? { pid: firstProcess.pid, startTicks: firstProcess.startTicks, ticks: firstProcess.ticks }
        : null,
    };
  }
  return value;
}

/**
 * One-second cache inside this plugin process. The installation is bound to one
 * daemon host, so the reading never needs a host key.
 */
export function readHostResources(_input: unknown, _context: PluginHandlerContext): Promise<HostResources> {
  const now = Date.now();
  if (cached && now - cached.at < CACHE_MS) return Promise.resolve(cached.value);
  if (inflight) return inflight;
  inflight = sample()
    .then((value) => {
      cached = { at: Date.now(), value };
      return value;
    })
    .finally(() => {
      inflight = null;
    });
  return inflight;
}
