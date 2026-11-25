import os from "node:os";
import type { PluginHandlerContext } from "@getpaseo/plugin/server";
import {
  clampPercent,
  cpuUsagePercent,
  deltaWindow,
  diskTotals,
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
import { DEFAULT_SETTINGS, type MonitorSettings } from "../shared/settings.ts";
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

/** Default fast cadence; the stored setting may be 5 s or 10 s instead. */
export const SAMPLE_MS = 2_000;
/** Disks change slowly and statfs across many mounts is not free. */
export const DISK_MS = 30_000;
/** About three minutes, independent of the chosen cadence. */
export const HISTORY_WINDOW_MS = 3 * 60_000;
/** Hard cap on stored points so a 2 s cadence cannot grow past 90. */
export const HISTORY_LIMIT = Math.round(HISTORY_WINDOW_MS / 2000);
/** Stop the shared loop when no client has asked for a sample recently. */
const IDLE_STOP_MS = 30_000;
/**
 * Counter deltas older than this are a resume gap, not a current reading: the
 * percentage would average the whole idle period. Such a delta is reported as
 * null and the history keeps a visible hole instead of a fake bridge.
 */
/** A delta may span up to a few configured intervals before it is a gap. */
function maxDeltaMs(): number {
  return intervalMs * 3;
}
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
  /** Aggregate disk percentage, sampled with the 30 s disk cadence. */
  diskPercent: number | null;
}

interface DiskState {
  atMono: number;
  entries: DiskEntry[] | null;
  scope: "local-mounts" | "root-only";
  /** Root reading taken in the same 30 s pass, so the fast path never statfs's. */
  root: Awaited<ReturnType<typeof readSystemDisk>> | null;
  rootIsStale: boolean;
}

let baseline: CounterBaseline | null = null;
let latest: HostResources | null = null;
/** Cadence currently in force; changed live from the host-scoped settings. */
let intervalMs: number = DEFAULT_SETTINGS.intervalMs;
/** Monotonic time `latest` was produced; a resume must not serve an old payload. */
let latestMono = 0;
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
 * Both the disk rows and the root reading refresh together every 30 s, so the
 * 2 s fast path never repeats a statfs. If a refresh fails, the previous rows
 * and root figure are reused rather than dropped; the flags say they are old.
 */
async function refreshDisks(nowMono: number): Promise<DiskState> {
  if (diskState && nowMono - diskState.atMono < DISK_MS) return diskState;
  const [entries, root] = await Promise.all([
    readLocalDisks().catch(() => null),
    readSystemDisk().catch(() => null),
  ]);
  const usable = entries && entries.length > 0 ? entries : null;
  const next: DiskState = {
    atMono: nowMono,
    entries: usable ?? diskState?.entries ?? null,
    scope: usable ? "local-mounts" : "root-only",
    root: root ?? diskState?.root ?? null,
    rootIsStale: root === null && diskState?.root != null,
  };
  diskState = next;
  return next;
}

/** Aggregate disk figure with an explicit scope; the root fallback is labelled. */
function diskTotalValue(disks: DiskState): HostResources["diskTotal"] {
  if (disks.entries) {
    const totals = diskTotals(disks.entries);
    return totals ? { scope: "local-disks", ...totals } : null;
  }
  const root = disks.root ? diskUsage(disks.root) : null;
  return root
    ? { scope: "root-disk", usedBytes: root.usedBytes, availableBytes: root.availableBytes, percent: root.percent }
    : null;
}

/** One pass over every counter. Returns null only if even CPU failed outright. */
async function tick(): Promise<HostResources | null> {
  const startedMono = monotonicMs();
  const firstCpu = await readCpu();
  const firstProcess = await readDaemonProcess();
  const memory = await readMemorySnapshot();
  const memoryDetail = process.platform === "linux" ? await readMemoryDetail().catch(() => null) : null;
  // One macOS read feeds both the used figure and the cached/pressure fields.
  const mac = process.platform === "darwin" ? await readMacMemory().catch(() => null) : null;
  // Failures stay isolated per collector: no counter can null out another.
  const network = await readNetDev().catch(() => null);
  const uptimeSeconds = await readUptime().catch(() => null);
  const loadAverage = await readLoadAverage().catch(() => null);
  const disks = await refreshDisks(startedMono);

  const record = (previous: CounterBaseline | null, cpu: typeof firstCpu, daemon: typeof firstProcess): HostResources | null => {
    const nowMono = monotonicMs();
    // A resumed loop after an idle stop would otherwise show a many-minute
    // average as "now". Anything past a few sample intervals is a gap.
    const { withinCadence, windowMs: elapsed } = deltaWindow(previous?.atMono ?? null, nowMono, maxDeltaMs());
    const comparable = withinCadence && previous !== null && cpu !== null && previous.source === cpu.source;
    const hostTicks = comparable && previous !== null ? cpu.times.total - previous.times.total : 0;
    // The RPC contract types these windows as whole milliseconds; the
    // monotonic delta itself is fractional.
    const windowMs = comparable ? Math.round(elapsed) : 0;
    const memoryUsedBytes = memory.availableBytes === null ? null : Math.max(0, memory.totalBytes - memory.availableBytes);
    // Root disk comes from the same 30 s pass; it is not re-read every 2 s.
    const diskUse = disks.root ? diskUsage(disks.root) : null;
    const diskTotal = diskTotalValue(disks);

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
        : withinCadence && previous?.network != null
          ? netRates(previous.network, network, elapsed)
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
        // It is a step function: identical between refreshes, never interpolated.
        diskPercent: diskTotal?.percent ?? null,
      },
      HISTORY_LIMIT,
    );
    // Drop points outside the three-minute window as well as by count, so a
    // resume after an idle stop cannot splice old points onto the new curve.
    const cutoff = Date.now() - HISTORY_WINDOW_MS;
    history = history.filter((point) => Date.parse(point.at) >= cutoff);

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
      diskTotal,
      memoryBreakdown: mac
        ? { cachedBytes: mac.cachedBytes, buffersBytes: null }
        : memoryDetail
          ? { cachedBytes: memoryDetail.cachedBytes, buffersBytes: memoryDetail.buffersBytes }
          : null,
      memoryPressure: mac?.pressure ?? null,
      history: { intervalMs, samples: history.slice() },
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
  scheduleNext();
}

/** Re-arm the single timer on the current cadence; chained, never overlapping. */
function scheduleNext(): void {
  const schedule = () => {
    if (!running) return;
    loopTimer = setTimeout(async () => {
      loopTimer = null;
      if (!running) return;
      // A timer left over from a cadence change must not start a second chain:
      // the tick already in flight re-arms the one chain when it finishes.
      if (ticking) return;
      ticking = true;
      try {
        const value = await tick();
        // A sampler stopped while this pass ran must not resurrect the payload.
        if (value && running) {
          latest = value;
          latestMono = monotonicMs();
        }
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
    }, intervalMs);
  };
  schedule();
}

/**
 * Apply a settings change without a reload: the next chained tick uses the new
 * cadence. A pending timer is re-armed so a shorter interval takes effect now.
 */
export function applySettings(next: Partial<MonitorSettings>): void {
  const desired = next.intervalMs ?? intervalMs;
  const changed = desired !== intervalMs;
  intervalMs = desired;
  if (!changed || !running) return;
  // Only a waiting timer needs re-arming. During a tick the in-flight chain
  // re-arms with the new cadence, so starting another chain here would double
  // the sampling rate.
  if (loopTimer) {
    clearTimeout(loopTimer);
    loopTimer = null;
    scheduleNext();
  }
}

export function currentIntervalMs(): number {
  return intervalMs;
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
  latestMono = 0;
  history = [];
  diskState = null;
}

export async function readHostResources(_input: unknown, _context: PluginHandlerContext): Promise<HostResources> {
  lastDemandMono = monotonicMs();
  ensureLoop();
  // Serve the shared payload only while it is current; after an idle stop it is
  // stale, so the caller waits for a fresh pass instead of seeing old numbers.
  if (latest && monotonicMs() - latestMono <= maxDeltaMs()) return latest;
  // First caller waits for the initial pass instead of inventing an empty one.
  if (ticking) {
    while (ticking) await new Promise((resolve) => setTimeout(resolve, 50));
    if (latest) return latest;
  }
  ticking = true;
  try {
    const value = await tick();
    if (value) {
      latest = value;
      latestMono = monotonicMs();
    }
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
    diskTotal: null,
    memoryBreakdown: null,
    memoryPressure: null,
    history: { intervalMs, samples: [] },
    process: null,
  };
}

/** Tests only: deterministic single pass without the background loop. */
export const __test = { tick, clampPercent };
