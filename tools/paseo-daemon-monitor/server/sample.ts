import os from "node:os";
import type { PluginHandlerContext } from "@getpaseo/plugin/server";
import {
  clampPercent,
  cpuUsagePercent,
  diskUsage,
  memoryUsagePercent,
  netRates,
  processCpuPercent,
  pushBounded,
  readCpuTimes,
  type CpuTimes,
  type NetTotals,
} from "../shared/aggregate.ts";
import type { HostResources } from "../shared/contract.ts";
import {
  readLoadAverage,
  readLocalDisks,
  readMacMemory,
  readMemory,
  readMemoryDetail,
  readNetDev,
  readProcStatCpu,
  readProcess,
  readSystemDisk,
  readUptime,
  type DiskEntry,
} from "./proc.ts";

/** Fast counters: CPU, memory and network. */
export const SAMPLE_MS = 2_000;
/** Disks change slowly and statfs across many mounts is not free. */
export const DISK_MS = 30_000;
/** About three minutes of fast samples at 2 s. */
export const HISTORY_LIMIT = Math.round((3 * 60_000) / SAMPLE_MS);
/** Stop the shared loop when no client has asked for a sample recently. */
const IDLE_STOP_MS = 30_000;
const PRIME_MS = 250;

/** The forked plugin worker's parent is the daemon; pin it once, never re-derive it. */
const DAEMON_PID = process.ppid > 0 ? process.ppid : null;

/** Monotonic milliseconds; wall-clock jumps must not distort the deltas. */
function monotonicMs(): number {
  return performance.now();
}

interface ProcessBaseline {
  pid: number;
  startTicks: number;
  ticks: number;
}

interface CounterBaseline {
  source: "proc" | "os";
  times: CpuTimes;
  process: ProcessBaseline | null;
  network: NetTotals | null;
  /** Monotonic time of this counter reading. */
  atMono: number;
}

export interface HistoryPoint {
  at: string;
  cpuPercent: number | null;
  memoryPercent: number | null;
  rxBytesPerSecond: number | null;
  txBytesPerSecond: number | null;
}

interface DiskState {
  atMono: number;
  entries: DiskEntry[] | null;
  scope: "local-mounts" | "root-only";
}

let baseline: CounterBaseline | null = null;
let latest: HostResources | null = null;
let history: HistoryPoint[] = [];
let diskState: DiskState | null = null;
let loopTimer: ReturnType<typeof setTimeout> | null = null;
let running = false;
let ticking = false;
let lastDemandMono = 0;

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
  if (process.platform === "darwin") {
    const mac = await readMacMemory().catch(() => null);
    if (mac?.usedBytes != null) {
      // Activity Monitor's Memory Used: app + wired + compressor. Cache is
      // reported separately, never folded into the used figure.
      return { totalBytes: os.totalmem(), availableBytes: Math.max(0, os.totalmem() - mac.usedBytes), basis: "available" };
    }
  }
  return { totalBytes: os.totalmem(), availableBytes: os.freemem(), basis: "free" };
}

/**
 * Disk rows are refreshed independently every 30 s. A failure keeps the root
 * reading and marks the scope accordingly; it never touches CPU or memory.
 */
async function refreshDisks(nowMono: number): Promise<DiskState> {
  if (diskState && nowMono - diskState.atMono < DISK_MS) return diskState;
  const entries = await readLocalDisks().catch(() => null);
  const next: DiskState = {
    atMono: nowMono,
    entries: entries && entries.length > 0 ? entries : null,
    scope: entries && entries.length > 0 ? "local-mounts" : "root-only",
  };
  diskState = next;
  return next;
}

/** One pass over every counter. Returns null only if even CPU failed outright. */
async function tick(): Promise<HostResources | null> {
  const startedMono = monotonicMs();
  const firstCpu = await readCpu();
  const firstProcess = await readDaemonProcess();
  const memory = await readMemorySnapshot();
  const memoryDetail = process.platform === "linux" ? await readMemoryDetail().catch(() => null) : null;
  const mac = process.platform === "darwin" ? await readMacMemory().catch(() => null) : null;
  const rootDisk = await readSystemDisk().catch(() => null);
  // Failures stay isolated per collector: no counter can null out another.
  const network = await readNetDev().catch(() => null);
  const uptimeSeconds = await readUptime().catch(() => null);
  const loadAverage = await readLoadAverage().catch(() => null);
  const disks = await refreshDisks(startedMono);

  const record = (previous: CounterBaseline | null, cpu: typeof firstCpu, daemon: typeof firstProcess): HostResources | null => {
    const nowMono = monotonicMs();
    const comparable = previous !== null && cpu !== null && previous.source === cpu.source;
    const hostTicks = comparable ? cpu.times.total - previous.times.total : 0;
    const windowMs = comparable ? Math.max(0, nowMono - previous.atMono) : 0;
    const memoryUsedBytes = memory.availableBytes === null ? null : Math.max(0, memory.totalBytes - memory.availableBytes);
    const diskUse = rootDisk ? diskUsage(rootDisk) : null;

    let processValue: HostResources["process"] = null;
    if (daemon) {
      const prior = previous?.process ?? null;
      const same = prior !== null && prior.pid === daemon.pid && prior.startTicks === daemon.startTicks;
      processValue = {
        pid: daemon.pid,
        cpuPercent:
          same && previous?.source === "proc" && cpu?.source === "proc"
            ? processCpuPercent(prior.ticks, daemon.ticks, hostTicks)
            : null,
        rssBytes: daemon.rssBytes,
      };
    }

    // A missing baseline, changed interface set or backwards counter yields
    // nulls; a genuinely idle host yields a real 0.
    const networkRates =
      network === null
        ? null
        : previous?.network != null
          ? netRates(previous.network, network, windowMs)
          : { rxBytesPerSecond: null, txBytesPerSecond: null };

    const cpuPercent = comparable ? cpuUsagePercent(previous.times, cpu.times) : null;
    const memoryPercent = memoryUsagePercent(memory.totalBytes, memory.availableBytes);

    const diskRows = disks.entries
      ? disks.entries
      : diskUse
        ? [
            {
              mountPoint: "/",
              source: "root",
              fstype: "unknown",
              totalBytes: diskUse.totalBytes,
              usedBytes: diskUse.usedBytes,
              availableBytes: diskUse.availableBytes,
              percent: diskUse.percent,
            },
          ]
        : null;

    history = pushBounded(
      history,
      {
        at: new Date().toISOString(),
        cpuPercent,
        memoryPercent,
        rxBytesPerSecond: networkRates?.rxBytesPerSecond ?? null,
        txBytesPerSecond: networkRates?.txBytesPerSecond ?? null,
      },
      HISTORY_LIMIT,
    );

    return {
      sampledAt: new Date().toISOString(),
      platform: process.platform,
      cpuCores: os.cpus().length,
      cpuSource: cpu?.source ?? "os",
      cpuPercent,
      cpuWindowMs: windowMs,
      memoryPercent,
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
      network: networkRates
        ? { ...networkRates, windowMs }
        : null,
      uptimeSeconds,
      loadAverage,
      disks: diskRows,
      diskScope: disks.entries ? "local-mounts" : "root-only",
      memoryBreakdown: mac
        ? { cachedBytes: mac.cachedBytes, buffersBytes: null }
        : memoryDetail
          ? { cachedBytes: memoryDetail.cachedBytes, buffersBytes: memoryDetail.buffersBytes }
          : null,
      memoryPressure: mac?.pressure ?? null,
      history: { intervalMs: SAMPLE_MS, samples: history.slice() },
      process: processValue,
    };
  };

  if (!baseline && firstCpu) {
    // No earlier counter: take a second reading inside this pass so a fresh
    // daemon never advertises a fabricated 0% before its first interval.
    await new Promise((resolve) => setTimeout(resolve, PRIME_MS));
    const secondCpu = await readCpu();
    const secondProcess = await readDaemonProcess();
    const value = record(
      {
        source: firstCpu.source,
        times: firstCpu.times,
        atMono: startedMono,
        process: firstProcess
          ? { pid: firstProcess.pid, startTicks: firstProcess.startTicks, ticks: firstProcess.ticks }
          : null,
        network: null,
      },
      secondCpu,
      secondProcess,
    );
    const stored = secondCpu ?? firstCpu;
    baseline = {
      source: stored.source,
      times: stored.times,
      atMono: monotonicMs(),
      process: secondProcess
        ? { pid: secondProcess.pid, startTicks: secondProcess.startTicks, ticks: secondProcess.ticks }
        : null,
      network,
    };
    return value;
  }

  const value = record(baseline, firstCpu, firstProcess);
  if (firstCpu) {
    baseline = {
      source: firstCpu.source,
      times: firstCpu.times,
      atMono: monotonicMs(),
      process: firstProcess
        ? { pid: firstProcess.pid, startTicks: firstProcess.startTicks, ticks: firstProcess.ticks }
        : null,
      network,
    };
  }
  return value;
}

/**
 * The single shared sampling loop for this daemon plugin instance. Ticks are
 * chained after the previous one finishes, so a slow pass never overlaps the
 * next one; the loop stops itself once no client has requested data for a while.
 */
function ensureLoop(): void {
  if (running) return;
  running = true;
  const schedule = () => {
    if (!running) return;
    loopTimer = setTimeout(async () => {
      loopTimer = null;
      if (!running) return;
      if (ticking) return schedule();
      ticking = true;
      try {
        const value = await tick();
        if (value) latest = value;
      } catch {
        // A failed pass keeps the last good payload; the next tick retries.
      } finally {
        ticking = false;
      }
      if (monotonicMs() - lastDemandMono >= IDLE_STOP_MS) {
        stopLoop();
        return;
      }
      schedule();
    }, SAMPLE_MS);
  };
  schedule();
}

function stopLoop(): void {
  running = false;
  if (loopTimer) clearTimeout(loopTimer);
  loopTimer = null;
}

/** Bound the loop to the plugin instance: a reload drops the old timer. */
export function stopSampler(): void {
  stopLoop();
  baseline = null;
  latest = null;
  history = [];
  diskState = null;
}

export async function readHostResources(_input: unknown, _context: PluginHandlerContext): Promise<HostResources> {
  lastDemandMono = monotonicMs();
  ensureLoop();
  if (latest) return latest;
  // First caller waits for the initial pass instead of inventing an empty one.
  if (ticking) {
    while (ticking) await new Promise((resolve) => setTimeout(resolve, 50));
    if (latest) return latest;
  }
  ticking = true;
  try {
    const value = await tick();
    if (value) latest = value;
  } finally {
    ticking = false;
  }
  return latest ?? emptyReading();
}

/** Only reachable if a brand-new daemon cannot read even CPU. */
function emptyReading(): HostResources {
  return {
    sampledAt: new Date().toISOString(),
    platform: process.platform,
    cpuCores: Math.max(1, os.cpus().length),
    cpuSource: "os",
    cpuPercent: null,
    cpuWindowMs: 0,
    memoryPercent: null,
    memoryUsedBytes: null,
    memoryTotalBytes: Math.max(0, os.totalmem()),
    memoryBasis: "free",
    disk: null,
    network: null,
    uptimeSeconds: null,
    loadAverage: null,
    disks: null,
    diskScope: "root-only",
    memoryBreakdown: null,
    memoryPressure: null,
    history: { intervalMs: SAMPLE_MS, samples: [] },
    process: null,
  };
}

/** Tests only: deterministic single pass without the background loop. */
export const __test = { tick, clampPercent };
