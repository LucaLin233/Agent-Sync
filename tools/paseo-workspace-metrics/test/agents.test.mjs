import assert from "node:assert/strict";
import { test } from "node:test";
import { pillTarget } from "../shared/agents.ts";

test("composer pills follow live agents in their own workspace", () => {
  assert.deepEqual(pillTarget({ id: "a", workspaceId: "w" }), { id: "a", workspaceId: "w" });
});

test("archived, background, and detached agents have no pill", () => {
  assert.equal(pillTarget({ id: "a" }), null);
  assert.equal(pillTarget({ id: "a", workspaceId: null }), null);
  assert.equal(pillTarget({ id: "a", workspaceId: "w", archivedAt: "2026-11-22T00:00:00Z" }), null);
  assert.equal(pillTarget({ id: "a", workspaceId: "w", background: true }), null);
});
