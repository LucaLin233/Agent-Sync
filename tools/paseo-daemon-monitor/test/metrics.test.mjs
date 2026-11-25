import assert from "node:assert/strict";
import test from "node:test";

import {
  dfPercent,
  localMounts,
  parseLoadAverage,
  parseMeminfoDetail,
  parseMemoryPressure,
  parseUptime,
  parseVmStat,
  pushBounded,
} from "../shared/aggregate.ts";

test("bounded history drops oldest and keeps insertion order", () => {
  let list = [];
  for (let i = 0; i < 5; i += 1) list = pushBounded(list, i, 3);
  assert.deepEqual(list, [2, 3, 4]);
  assert.deepEqual(pushBounded([], 1, 0), []);
});

test("load average and uptime parse or return null", () => {
  assert.deepEqual(parseLoadAverage("0.52 0.41 0.33 2/567 8901"), { one: 0.52, five: 0.41, fifteen: 0.33 });
  assert.equal(parseLoadAverage("bogus"), null);
  assert.equal(parseUptime("12345.67 98765.43"), 12345.67);
  assert.equal(parseUptime("x"), null);
});

test("meminfo detail splits cached and buffers", () => {
  const text = "MemTotal: 100 kB\nMemAvailable: 40 kB\nBuffers: 10 kB\nCached: 25 kB\n";
  assert.deepEqual(parseMeminfoDetail(text), { cachedBytes: 25 * 1024, buffersBytes: 10 * 1024 });
  assert.equal(parseMeminfoDetail("MemTotal: 1 kB"), null);
});

test("local mount filter keeps block devices and ZFS, drops the rest", () => {
  const text = [
    "proc /proc proc rw 0 0",
    "tmpfs /run tmpfs rw 0 0",
    "/dev/sda1 / ext4 rw 0 0",
    "/dev/sdb1 /mnt/data xfs rw 0 0",
    "tank/home /tank/home zfs rw 0 0",
    "server:/export /nfs nfs4 rw 0 0",
    "/dev/loop0 /snap/core squashfs ro 0 0",
    "/dev/sr0 /media/cdrom iso9660 ro 0 0",
    "/dev/sda1 /boot ext4 rw 0 0",
    "overlay /var/lib/docker/overlay2/x overlay rw 0 0",
  ].join("\n");
  // Sorted by path length; /dev/sda1 keeps its shortest mount point, so /boot drops.
  assert.deepEqual(localMounts(text).map((m) => m.mountPoint), ["/", "/mnt/data", "/tank/home"]);
});

test("df percent excludes reserved space from both used and free", () => {
  assert.equal(dfPercent(50, 50), 50);
  assert.equal(dfPercent(0, 100), 0);
  assert.equal(dfPercent(10, 0), 100);
  assert.equal(dfPercent(0, 0), null);
});

test("vm_stat maps Activity Monitor components with the reported page size", () => {
  const text = [
    "Mach Virtual Memory Statistics: (page size of 16384 bytes)",
    "Pages free: 1000.",
    "Pages active: 2000.",
    "Pages inactive: 500.",
    "Pages wired down: 800.",
    "Pages purgeable: 100.",
    "Pages occupied by compressor: 200.",
  ].join("\n");
  const memory = parseVmStat(text, 16384);
  assert.equal(memory.appBytes, 2000 * 16384);
  assert.equal(memory.wiredBytes, 800 * 16384);
  assert.equal(memory.compressedBytes, 200 * 16384);
  assert.equal(memory.cachedBytes, 600 * 16384);
  assert.equal(memory.usedBytes, 3000 * 16384);
  assert.equal(parseVmStat(text, 0), null);
});

test("macOS memory pressure maps warning and critical", () => {
  assert.equal(parseMemoryPressure("1"), "normal");
  assert.equal(parseMemoryPressure("2\n"), "warning");
  assert.equal(parseMemoryPressure("4"), "critical");
  assert.equal(parseMemoryPressure("3"), null);
});
