import assert from "node:assert/strict";
import test from "node:test";

import { INTERVAL_OPTIONS, monitorSettings, parseInterval } from "../shared/settings.ts";

test("settings default to a 2 s cadence with the footer rate group on", () => {
  const values = monitorSettings.schema.parse({});
  assert.deepEqual(values, { intervalMs: 2000, showNetworkInFooter: true });
  assert.equal(monitorSettings.scope, "host");
  assert.equal(monitorSettings.version, 1);
});

test("only the three documented cadences are accepted", () => {
  assert.deepEqual(monitorSettings.schema.parse({ intervalMs: 5000 }).intervalMs, 5000);
  assert.deepEqual(monitorSettings.schema.parse({ intervalMs: 10000 }).intervalMs, 10000);
  assert.throws(() => monitorSettings.schema.parse({ intervalMs: 3000 }));
  assert.throws(() => monitorSettings.schema.parse({ intervalMs: "2000" }));
});

test("the select values round-trip to milliseconds and unknown input falls back", () => {
  assert.deepEqual(INTERVAL_OPTIONS.map((option) => option.value), ["2000", "5000", "10000"]);
  for (const option of INTERVAL_OPTIONS) {
    assert.equal(String(parseInterval(option.value)), option.value);
  }
  assert.equal(parseInterval("3000"), 2000);
  assert.equal(parseInterval(undefined), 2000);
  assert.equal(parseInterval("not-a-number"), 2000);
});

test("the footer switch is a boolean and rejects other types", () => {
  assert.equal(monitorSettings.schema.parse({ showNetworkInFooter: false }).showNetworkInFooter, false);
  assert.throws(() => monitorSettings.schema.parse({ showNetworkInFooter: "off" }));
});
