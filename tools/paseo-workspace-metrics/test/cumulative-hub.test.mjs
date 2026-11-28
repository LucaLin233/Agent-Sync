import assert from "node:assert/strict";
import { test } from "node:test";
import { createCumulativeHub } from "../client/cumulative-hub.ts";

const WS = "wks_hub";

test("the first accepted reply wins when the newer request has not answered", () => {
  const hub = createCumulativeHub();
  const older = hub.begin(WS);
  const newer = hub.begin(WS);
  // The earlier read returns first with a valid reading.
  assert.equal(hub.publish(WS, older, { rate: 0.962, error: null }), true);
  assert.deepEqual(hub.read(WS), { rate: 0.962, error: null });
  // A late reply from the newer request still replaces an older reading.
  assert.equal(hub.publish(WS, newer, { rate: 0.971, error: null }), true);
  assert.equal(hub.read(WS).rate, 0.971);
  // The older request cannot land afterwards.
  assert.equal(hub.publish(WS, older, { rate: 0.801, error: null }), false);
  assert.equal(hub.read(WS).rate, 0.971);
});

test("a newer request that answers first is not overwritten by the older one", () => {
  const hub = createCumulativeHub();
  const older = hub.begin(WS);
  const newer = hub.begin(WS);
  assert.equal(hub.publish(WS, newer, { rate: 0.2, error: null }), true);
  assert.equal(hub.publish(WS, older, { rate: 0.8, error: null }), false);
  assert.equal(hub.read(WS).rate, 0.2);
});

test("a real zero is a published reading, not a missing one", () => {
  const hub = createCumulativeHub();
  assert.equal(hub.publish(WS, hub.begin(WS), { rate: 0, error: null }), true);
  assert.deepEqual(
    { rate: hub.read(WS).rate, error: hub.read(WS).error },
    { rate: 0, error: null },
  );
});

test("a failed read from a stale scope never lands", () => {
  const hub = createCumulativeHub();
  hub.publish(WS, hub.begin(WS), { rate: 0.962, error: null });
  const stale = hub.begin(WS);
  // A settings generation change or a member change voids reads already started.
  hub.clearAll();
  assert.equal(hub.publish(WS, stale, { rate: null, error: "late" }), false);
  assert.equal(hub.read(WS), undefined);
});

test("clearing a member change keeps the reading but voids in-flight replies", () => {
  const hub = createCumulativeHub();
  hub.publish(WS, hub.begin(WS), { rate: 0, error: null });
  const stale = hub.begin(WS);
  hub.invalidate(WS);
  assert.equal(hub.read(WS).rate, 0, "the shown reading survives a member change");
  assert.equal(hub.publish(WS, stale, { rate: 0.5, error: null }), false);
});

test("subscribers hear every accepted reading until they unsubscribe", () => {
  const hub = createCumulativeHub();
  let changes = 0;
  const stop = hub.subscribeAll(() => { changes += 1; });
  hub.publish(WS, hub.begin(WS), { rate: 0.5, error: null });
  assert.equal(changes, 1);
  stop();
  hub.publish(WS, hub.begin(WS), { rate: 0.6, error: null });
  assert.equal(changes, 1);
});
