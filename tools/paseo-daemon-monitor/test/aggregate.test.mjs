import assert from "node:assert/strict";
import test from "node:test";

import {
  cpuUsagePercent,
  diskUsage,
  memoryUsagePercent,
  parseMeminfo,
  parseProcStat,
  parseProcStatCpu,
  parseProcNetDev,
  parseVmRss,
  netRates,
  processCpuPercent,
} from "../shared/aggregate.ts";

test("CPU delta reports all-core busy share and nulls zero windows", () => {
  const previous = { idle: 1000, total: 4000 };
  assert.equal(cpuUsagePercent(previous, { idle: 1100, total: 4400 }), 75);
  assert.equal(cpuUsagePercent(previous, { idle: 1000, total: 4000 }), null);
});

test("process CPU uses host ticks, not one core", () => {
  assert.equal(processCpuPercent(100, 112, 400), 3);
  assert.equal(processCpuPercent(100, 112, 0), null);
  assert.equal(processCpuPercent(100, 90, 400), null);
});

test("/proc/stat aggregate line counts iowait as idle", () => {
  const text = "cpu  10 2 30 400 8 1 2 0 0 0\ncpu0 1 0 1 40 0 0 0 0 0 0\n";
  assert.deepEqual(parseProcStatCpu(text), { idle: 408, total: 453 });
  assert.equal(parseProcStatCpu("intr 1 2 3"), null);
});

test("memory uses MemAvailable and clamps", () => {
  const parsed = parseMeminfo("MemTotal:       16384000 kB\nMemFree:         100000 kB\nMemAvailable:    8192000 kB\n");
  assert.deepEqual(parsed, { totalBytes: 16384000 * 1024, availableBytes: 8192000 * 1024 });
  assert.equal(memoryUsagePercent(1000, 250), 75);
  assert.equal(memoryUsagePercent(1000, null), null);
  assert.equal(memoryUsagePercent(0, 10), null);
  assert.equal(parseMeminfo("MemTotal: nope"), null);
});

test("/proc/<pid>/stat and status parse without the comm field", () => {
  const stat = "42 (paseo (daemon)) S 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 123456 20 21";
  assert.deepEqual(parseProcStat(stat), { ticks: 23, startTicks: 123456 });
  assert.equal(parseVmRss("Name:\tpaseo\nVmRSS:\t  20480 kB\n"), 20480 * 1024);
  assert.equal(parseVmRss("VmRSS: nope"), null);
});

test("disk share uses statfs blocks and keeps bavail separate", () => {
  const usage = diskUsage({ blocks: 1000, bfree: 300, bavail: 250, bsize: 1024 });
  assert.equal(usage.totalBytes, 1024000);
  assert.equal(usage.usedBytes, 700 * 1024);
  assert.equal(usage.availableBytes, 250 * 1024);
  assert.equal(usage.percent, 70);
  assert.equal(diskUsage({ blocks: 0, bfree: 0, bavail: 0, bsize: 4096 }).percent, null);
});

test("/proc/net/dev sums physical interfaces and skips loopback and virtual peers", () => {
  const text = [
    "Inter-|   Receive                                                |  Transmit",
    " face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed",
    "    lo: 5000 1 0 0 0 0 0 0 5000 1 0 0 0 0 0 0",
    "  eth0: 1000 1 0 0 0 0 0 0 2000 1 0 0 0 0 0 0",
    "  eth1: 300 1 0 0 0 0 0 0 400 1 0 0 0 0 0 0",
    "veth12ab: 9999 1 0 0 0 0 0 0 9999 1 0 0 0 0 0 0",
    "docker0: 8888 1 0 0 0 0 0 0 8888 1 0 0 0 0 0 0",
    "br-abc123: 7777 1 0 0 0 0 0 0 7777 1 0 0 0 0 0 0",
  ].join("\n");
  assert.deepEqual(parseProcNetDev(text), { rxBytes: 1300, txBytes: 2400, interfaces: ["eth0", "eth1"] });
});

test("network rates use the monotonic window and refuse unusable baselines", () => {
  const before = { rxBytes: 1000, txBytes: 2000, interfaces: ["eth0"] };
  const after = { rxBytes: 3000, txBytes: 2500, interfaces: ["eth0"] };
  assert.deepEqual(netRates(before, after, 2000), { rxBytesPerSecond: 1000, txBytesPerSecond: 250 });
  // Idle is a real zero, not unknown.
  assert.deepEqual(netRates(before, before, 5000), { rxBytesPerSecond: 0, txBytesPerSecond: 0 });
  // Counter reset and interface change invalidate the delta.
  assert.deepEqual(netRates(after, before, 1000), { rxBytesPerSecond: null, txBytesPerSecond: null });
  assert.deepEqual(netRates(before, { ...after, interfaces: ["eth0", "eth1"] }, 1000), {
    rxBytesPerSecond: null,
    txBytesPerSecond: null,
  });
  assert.deepEqual(netRates(before, after, 0), { rxBytesPerSecond: null, txBytesPerSecond: null });
});
