/**
 * Pure arithmetic and /proc text parsers shared by the daemon sampler and its
 * tests. Nothing here touches the filesystem, so both bundles may import it.
 */

export interface CpuTimes {
  idle: number;
  total: number;
}

export function readCpuTimes(
  cpus: readonly { times: { user: number; nice: number; sys: number; idle: number; irq: number } }[],
): CpuTimes {
  let idle = 0;
  let total = 0;
  for (const cpu of cpus) {
    const t = cpu.times;
    idle += t.idle;
    total += t.user + t.nice + t.sys + t.idle + t.irq;
  }
  return { idle, total };
}

/** Aggregate "cpu" line of /proc/stat, in USER_HZ ticks (iowait counts as idle). */
export function parseProcStatCpu(text: string): CpuTimes | null {
  const line = text.split("\n").find((entry) => entry.startsWith("cpu "));
  if (!line) return null;
  const values = line.trim().split(/\s+/).slice(1).map(Number);
  if (values.length < 4 || values.some((value) => !Number.isFinite(value) || value < 0)) return null;
  const [user, nice, system, idle, iowait = 0, irq = 0, softirq = 0, steal = 0] = values;
  return {
    idle: idle + iowait,
    total: user + nice + system + idle + iowait + irq + softirq + steal,
  };
}

/** Percent of all logical cores busy between two readings of the same counter. */
export function cpuUsagePercent(previous: CpuTimes, current: CpuTimes): number | null {
  const total = current.total - previous.total;
  if (!(total > 0)) return null;
  const idle = Math.max(0, current.idle - previous.idle);
  return clampPercent(100 * (1 - idle / total));
}

/**
 * Daemon process CPU as a share of all host cores: process ticks over host ticks.
 * Both figures must come from the same /proc counter family.
 */
export function processCpuPercent(previousProcessTicks: number, currentProcessTicks: number, hostTicks: number): number | null {
  if (!(hostTicks > 0)) return null;
  const ticks = currentProcessTicks - previousProcessTicks;
  if (ticks < 0) return null;
  return clampPercent((100 * ticks) / hostTicks);
}

/** Used share from the available (not free) figure. */
export function memoryUsagePercent(totalBytes: number, availableBytes: number | null): number | null {
  if (!(totalBytes > 0) || availableBytes === null || !Number.isFinite(availableBytes)) return null;
  const available = Math.min(Math.max(availableBytes, 0), totalBytes);
  return clampPercent(100 * (1 - available / totalBytes));
}

export function parseMeminfo(text: string): { totalBytes: number; availableBytes: number | null } | null {
  let totalKb: number | null = null;
  let availableKb: number | null = null;
  for (const line of text.split("\n")) {
    const match = /^(MemTotal|MemAvailable):\s+(\d+)\s+kB$/.exec(line.trim());
    if (!match) continue;
    if (match[1] === "MemTotal") totalKb = Number(match[2]);
    else availableKb = Number(match[2]);
  }
  if (totalKb === null || !(totalKb > 0)) return null;
  return { totalBytes: totalKb * 1024, availableBytes: availableKb === null ? null : availableKb * 1024 };
}

/** utime, stime and starttime from /proc/<pid>/stat, after the comm field. */
export function parseProcStat(text: string): { ticks: number; startTicks: number } | null {
  const close = text.lastIndexOf(")");
  if (close < 0) return null;
  const fields = text.slice(close + 1).trim().split(/\s+/);
  const utime = Number(fields[11]);
  const stime = Number(fields[12]);
  const startTicks = Number(fields[19]);
  if (![utime, stime, startTicks].every(Number.isFinite)) return null;
  return { ticks: utime + stime, startTicks };
}

export function parseVmRss(text: string): number | null {
  const match = /^VmRSS:\s+(\d+)\s+kB$/m.exec(text);
  if (!match) return null;
  const kb = Number(match[1]);
  return Number.isFinite(kb) && kb >= 0 ? kb * 1024 : null;
}

/** Capacity of the filesystem that holds the system root, as fs.statfs reports it. */
export function diskUsage(input: { blocks: number; bfree: number; bavail: number; bsize: number }): {
  totalBytes: number;
  usedBytes: number;
  availableBytes: number;
  percent: number | null;
} {
  const { blocks, bfree, bavail, bsize } = input;
  if (!(blocks > 0) || !(bsize > 0) || !Number.isFinite(bfree)) {
    return { totalBytes: 0, usedBytes: 0, availableBytes: 0, percent: null };
  }
  const totalBytes = blocks * bsize;
  const usedBytes = Math.max(0, (blocks - bfree) * bsize);
  return {
    totalBytes,
    usedBytes,
    availableBytes: Math.max(0, bavail * bsize),
    percent: clampPercent((100 * usedBytes) / totalBytes),
  };
}

export function clampPercent(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.min(100, Math.max(0, Math.round(value * 10) / 10));
}

/** Virtual/container interfaces that duplicate the physical counters. */
const VIRTUAL_IFACE = /^(lo|veth.+|docker.+|br-.+|virbr.+|cni.+|flannel.+|tunl.+|vxlan.+|kube.+|cali.+|weave.+|podman.+|lxc.+|lxd.+|dummy.+|ifb.+|docker0|br0)$/;

export interface NetTotals {
  rxBytes: number;
  txBytes: number;
  /** Sorted interface names that contributed; a change voids the baseline. */
  interfaces: string[];
}

/**
 * Sum rx/tx byte counters from /proc/net/dev for physical interfaces only.
 * Loopback and known virtual/bridge devices are skipped so a container veth is
 * not counted a second time alongside its host-side peer.
 */
export function parseProcNetDev(text: string): NetTotals | null {
  const interfaces: string[] = [];
  let rxBytes = 0;
  let txBytes = 0;
  for (const raw of text.split("\n")) {
    const colon = raw.indexOf(":");
    if (colon < 0) continue;
    const name = raw.slice(0, colon).trim();
    if (!name || name === "Inter-|" || name === "face") continue;
    if (VIRTUAL_IFACE.test(name)) continue;
    const fields = raw.slice(colon + 1).trim().split(/\s+/).map(Number);
    if (fields.length < 9) continue;
    const [rx, , , , , , , , tx] = fields;
    if (!Number.isFinite(rx) || !Number.isFinite(tx) || rx < 0 || tx < 0) continue;
    interfaces.push(name);
    rxBytes += rx;
    txBytes += tx;
  }
  if (interfaces.length === 0) return { rxBytes: 0, txBytes: 0, interfaces: [] };
  interfaces.sort();
  return { rxBytes, txBytes, interfaces };
}

/**
 * Per-second rates between two counter readings over a monotonic window.
 * A changed interface set or a backwards counter means the old baseline is
 * void: rates stay null instead of reporting a fabricated spike.
 */
export function netRates(
  previous: NetTotals,
  current: NetTotals,
  windowMs: number,
): { rxBytesPerSecond: number | null; txBytesPerSecond: number | null } {
  const sameInterfaces =
    previous.interfaces.length === current.interfaces.length &&
    previous.interfaces.every((name, index) => name === current.interfaces[index]);
  if (!sameInterfaces || !(windowMs > 0)) return { rxBytesPerSecond: null, txBytesPerSecond: null };
  const rx = current.rxBytes - previous.rxBytes;
  const tx = current.txBytes - previous.txBytes;
  if (rx < 0 || tx < 0) return { rxBytesPerSecond: null, txBytesPerSecond: null };
  return { rxBytesPerSecond: (rx * 1000) / windowMs, txBytesPerSecond: (tx * 1000) / windowMs };
}

/** Bounded ring helper: newest sample last, oldest dropped first. */
export function pushBounded<T>(list: readonly T[], entry: T, limit: number): T[] {
  if (!(limit > 0)) return [];
  const next = list.length >= limit ? list.slice(list.length - limit + 1) : list.slice();
  next.push(entry);
  return next;
}

/** 1/5/15 minute load averages from /proc/loadavg. */
export function parseLoadAverage(text: string): { one: number; five: number; fifteen: number } | null {
  const values = text.trim().split(/\s+/).slice(0, 3).map(Number);
  if (values.length < 3 || values.some((value) => !Number.isFinite(value) || value < 0)) return null;
  return { one: values[0], five: values[1], fifteen: values[2] };
}

/** Uptime in seconds from /proc/uptime. */
export function parseUptime(text: string): number | null {
  const value = Number(text.trim().split(/\s+/)[0]);
  return Number.isFinite(value) && value >= 0 ? value : null;
}

/** Cached/buffers share of /proc/meminfo, for the macOS-style breakdown on Linux. */
export function parseMeminfoDetail(text: string): { cachedBytes: number; buffersBytes: number } | null {
  let cachedKb: number | null = null;
  let buffersKb: number | null = null;
  for (const line of text.split("\n")) {
    const match = /^(Cached|Buffers):\s+(\d+)\s+kB$/.exec(line.trim());
    if (!match) continue;
    if (match[1] === "Cached") cachedKb = Number(match[2]);
    else buffersKb = Number(match[2]);
  }
  if (cachedKb === null && buffersKb === null) return null;
  return { cachedBytes: (cachedKb ?? 0) * 1024, buffersBytes: (buffersKb ?? 0) * 1024 };
}

const NETWORK_FSTYPES = new Set([
  "nfs", "nfs4", "cifs", "smb3", "smbfs", "sshfs", "fuse.sshfs", "glusterfs", "ceph", "9p", "afs", "afpfs", "davfs",
]);
const NON_DISK_FSTYPES = new Set([
  "proc", "sysfs", "devtmpfs", "devpts", "tmpfs", "ramfs", "cgroup", "cgroup2", "securityfs", "debugfs", "tracefs",
  "pstore", "bpf", "configfs", "fusectl", "mqueue", "hugetlbfs", "autofs", "binfmt_misc", "efivarfs", "squashfs",
  "iso9660", "overlay", "nsfs", "rpc_pipefs", "selinuxfs", "fuse.lxcfs", "fuse.gvfsd-fuse",
]);

export interface MountEntry {
  source: string;
  mountPoint: string;
  fstype: string;
}

/**
 * Parse /proc/mounts into the mounts that hold real local storage: block
 * devices, plus ZFS datasets. Network, memory-backed and read-only image
 * filesystems are dropped before any statfs call.
 */
export function localMounts(text: string): MountEntry[] {
  const seen = new Set<string>();
  const mounts: MountEntry[] = [];
  for (const raw of text.split("\n")) {
    const fields = raw.trim().split(/\s+/);
    if (fields.length < 3) continue;
    const [source, mountPoint, fstype] = fields;
    if (!source || !mountPoint.startsWith("/")) continue;
    if (NON_DISK_FSTYPES.has(fstype) || NETWORK_FSTYPES.has(fstype)) continue;
    const isBlock = source.startsWith("/dev/");
    const isZfs = fstype === "zfs" || fstype.startsWith("zfs");
    if (!isBlock && !isZfs) continue;
    // One entry per device: keep the shortest mount point.
    if (seen.has(source)) continue;
    seen.add(source);
    mounts.push({ source, mountPoint, fstype });
  }
  return mounts.sort((a, b) => a.mountPoint.length - b.mountPoint.length);
}

/** df semantics: reserved space counts as neither used nor available. */
export function dfPercent(usedBytes: number, availableBytes: number): number | null {
  const denominator = usedBytes + availableBytes;
  if (!(denominator > 0)) return null;
  return clampPercent((100 * usedBytes) / denominator);
}

/** Activity Monitor style memory from macOS vm_stat, with a page size in bytes. */
export function parseVmStat(text: string, pageSize: number): {
  appBytes: number | null;
  wiredBytes: number | null;
  compressedBytes: number | null;
  cachedBytes: number | null;
  usedBytes: number | null;
} | null {
  if (!(pageSize > 0)) return null;
  const pages: Record<string, number> = {};
  for (const line of text.split("\n")) {
    const match = /^"?([A-Za-z][A-Za-z _-]*)"?:\s+(\d+)\.?\s*$/.exec(line.trim());
    if (match) pages[match[1]] = Number(match[2]);
  }
  const page = (name: string): number | null => (Number.isFinite(pages[name]) ? pages[name] * pageSize : null);
  const active = page("Pages active");
  const wired = page("Pages wired down");
  const compressor = page("Pages occupied by compressor");
  const cachedRaw = (page("Pages inactive") ?? 0) + (page("Pages purgeable") ?? 0);
  const appBytes = active;
  const compressedBytes = compressor;
  const usedBytes =
    active === null || wired === null ? null : active + wired + (compressor ?? 0);
  return {
    appBytes,
    wiredBytes: wired,
    compressedBytes,
    cachedBytes: cachedRaw > 0 ? cachedRaw : null,
    usedBytes,
  };
}

/** macOS kernel memory pressure level: 1 normal, 2 warning, 4 critical. */
export function parseMemoryPressure(text: string): "normal" | "warning" | "critical" | null {
  const level = Number(text.trim());
  if (level === 1) return "normal";
  if (level === 2) return "warning";
  if (level === 4) return "critical";
  return null;
}
