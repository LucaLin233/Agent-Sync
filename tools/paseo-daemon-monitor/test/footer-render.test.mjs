import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

// The plan can be right while the component ignores it, so also check the
// rendered branch: which JSX block draws the two rates, which draws the clock,
// and that nothing gates the meter on `layout.compact` any more.
const source = readFileSync(new URL("../client/monitor.tsx", import.meta.url), "utf8");

test("the footer renders the network branch with stacked rates and short units", () => {
  assert.match(source, /plan\.tail === "network"/);
  assert.match(source, /plan\.tailStacked \? "column" : "row"/);
  assert.match(source, /↓\{shortRate\(value\?\.network\?\.rxBytesPerSecond\)\}/);
  assert.match(source, /↑\{shortRate\(value\?\.network\?\.txBytesPerSecond\)\}/);
});

test("the clock is only drawn for the time tail, never for compact", () => {
  // One clock call site, inside the fallback branch of the network ternary.
  assert.equal(source.match(/clockText\(value/g).length, 1);
  assert.match(source, /clockText\(value\.sampledAt, plan\.tailWidth\)/);
  assert.doesNotMatch(source, /layout\.compact[^,;)]*showTail/);
});

test("compact no longer disables meters or rates", () => {
  assert.doesNotMatch(source, /!layout\.compact/);
  assert.doesNotMatch(source, /fontScale <= 1\.4/);
  // Compact is still passed so the plan can stack the two rates and size the tail.
  assert.match(source, /compact: layout\.compact/);
});
