import assert from "node:assert/strict";
import test from "node:test";

import { hostResourcesRpc } from "../shared/contract.ts";

// The official RPC layer validates a handler's return value against the
// declared output schema. A payload that only looks right in TypeScript is
// still rejected at runtime, which is what left the client with no numbers.
test("a real Linux sample satisfies the declared RPC output schema", { skip: process.platform !== "linux" }, async () => {
  const { __test } = await import("../server/sample.ts");
  const value = await __test.tick();
  assert.ok(value, "tick() produced a payload");
  const parsed = hostResourcesRpc.output.safeParse(value);
  assert.equal(parsed.success, true, parsed.success ? "" : JSON.stringify(parsed.error.issues));
  assert.ok(Number.isInteger(value.cpuWindowMs), "cpuWindowMs is whole milliseconds");
  assert.ok(value.network === null || Number.isInteger(value.network.windowMs), "network.windowMs is whole milliseconds");
});

test("fractional counter windows are rejected, so the sampler must round them", { skip: process.platform !== "linux" }, async () => {
  const { __test } = await import("../server/sample.ts");
  const value = await __test.tick();
  assert.ok(value);
  const bad = { ...value, cpuWindowMs: value.cpuWindowMs + 0.5 };
  assert.equal(hostResourcesRpc.output.safeParse(bad).success, false);
  if (value.network) {
    const badNetwork = { ...value, network: { ...value.network, windowMs: value.network.windowMs + 0.5 } };
    assert.equal(hostResourcesRpc.output.safeParse(badNetwork).success, false);
  }
});

// The client never sees the raw payload: `useRpc` runs it through
// callPluginRpc, which awaits the daemon then validates the contract output.
// This is the exact path that silently failed while every number was "—".
test("the client-side contract decode accepts a real sample", { skip: process.platform !== "linux" }, async () => {
  const { __test } = await import("../server/sample.ts");
  const value = await __test.tick();
  assert.ok(value);
  // callPluginRpc() in the official SDK is `contract.output.parseAsync(invoke(...))`;
  // this is that operation without the transport, which is where the client
  // decode used to throw and blank every reading.
  const decoded = await hostResourcesRpc.output.parseAsync(value);
  assert.equal(decoded.cpuWindowMs, value.cpuWindowMs);
  assert.equal(decoded.sampledAt, value.sampledAt);
  assert.equal(decoded.history.intervalMs, value.history.intervalMs);
});
