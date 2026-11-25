import assert from "node:assert/strict";
import test from "node:test";

import {
  cpuUsagePercent,
  diskUsage,
  memoryUsagePercent,
  parseMeminfo,
  parseProcStat,
  parseProcStatCpu,
  parseVmRss,
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
