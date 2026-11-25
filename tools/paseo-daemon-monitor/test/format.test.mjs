import assert from "node:assert/strict";
import test from "node:test";

import { bytesText, loadText, percentText, rateText, shortRate, uptimeText } from "../client/format.ts";

test("a real zero is not confused with a missing sample", () => {
  assert.equal(percentText(0), "0%");
  assert.equal(percentText(null), "—");
  assert.equal(percentText(undefined), "—");
  assert.equal(shortRate(0), "0B");
  assert.equal(shortRate(null), "—");
  assert.equal(rateText(0), "0 B/s");
  assert.equal(rateText(null), "—");
});

test("footer rates use short binary units and the detail keeps the unit", () => {
  assert.equal(shortRate(1024), "1.0K");
  assert.equal(shortRate(640 * 1024), "640K");
  assert.equal(shortRate(2.4 * 1024 * 1024), "2.4M");
  assert.equal(shortRate(50 * 1024 ** 3), "50G");
  assert.equal(shortRate(2 * 1024 ** 3), "2G");
  // Even an absurd rate cannot stretch the footer label past a fixed bound.
  assert.equal(shortRate(1e15), "9990G");
  assert.equal(shortRate(1024 ** 2), "1.0M");
  // The widest short label stays bounded: arrow + 5 characters.
  assert.ok(shortRate(9.9 * 1024 ** 3).length <= 5);
  assert.equal(rateText(640 * 1024), "640 KiB/s");
  assert.equal(rateText(2.4 * 1024 * 1024), "2.4 MiB/s");
});

test("capacity, uptime and load format or stay empty", () => {
  assert.equal(bytesText(11.5 * 1024 ** 3), "11.5 GiB");
  assert.equal(bytesText(null), "—");
  assert.equal(uptimeText(6 * 86400 + 4 * 3600 + 22 * 60), "6 天 04:22");
  assert.equal(uptimeText(null), "—");
  assert.equal(loadText({ one: 1.28, five: 0.96, fifteen: 0.81 }), "1.28 / 0.96 / 0.81");
  assert.equal(loadText(null), "—");
});
