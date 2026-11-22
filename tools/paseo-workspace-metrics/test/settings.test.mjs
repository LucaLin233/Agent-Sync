import assert from "node:assert/strict";
import { test } from "node:test";
import { effectiveWorkspaceScope, workspaceInScope } from "../shared/scope.ts";

test("fresh settings default the cumulative feature off", () => {
  assert.deepEqual(effectiveWorkspaceScope({}), {
    enabled: false,
    allWorkspaces: false,
    workspaceIds: [],
    error: null,
  });
});

test("legacy all and allowlist documents keep their previous meaning", () => {
  assert.deepEqual(effectiveWorkspaceScope({ allWorkspaces: true }), {
    enabled: true,
    allWorkspaces: true,
    workspaceIds: [],
    error: null,
  });
  assert.deepEqual(effectiveWorkspaceScope({ workspaceIds: ["w2", "w1", "w2"] }), {
    enabled: true,
    allWorkspaces: false,
    workspaceIds: ["w2", "w1"],
    error: null,
  });
});

test("the explicit switch wins over every legacy field", () => {
  assert.deepEqual(effectiveWorkspaceScope({
    cumulativeEnabled: false,
    allWorkspaces: true,
    workspaceIds: ["w1"],
  }), {
    enabled: false,
    allWorkspaces: false,
    workspaceIds: [],
    error: null,
  });
  assert.deepEqual(effectiveWorkspaceScope({ cumulativeEnabled: true }), {
    enabled: true,
    allWorkspaces: true,
    workspaceIds: [],
    error: null,
  });
});

test("a restricted empty list reports an error and stays out of scope", () => {
  const scope = effectiveWorkspaceScope({ cumulativeEnabled: true, allWorkspaces: false, workspaceIds: [] });
  assert.equal(scope.enabled, true);
  assert.equal(scope.error, "至少填写一个 workspace ID");
  assert.equal(workspaceInScope({ ...scope, enabled: true }, "w1"), false);
});

test("one scope policy gates the panel and the pill", () => {
  const all = effectiveWorkspaceScope({ cumulativeEnabled: true });
  const one = effectiveWorkspaceScope({ cumulativeEnabled: true, workspaceIds: ["w1"] });
  assert.equal(workspaceInScope({ ...all, error: null, codexHomeConfigured: false }, "w9"), true);
  assert.equal(workspaceInScope({ ...one, error: null, codexHomeConfigured: false }, "w1"), true);
  assert.equal(workspaceInScope({ ...one, error: null, codexHomeConfigured: false }, "w2"), false);
  assert.equal(workspaceInScope({ ...all, enabled: false, error: null, codexHomeConfigured: false }, "w9"), false);
});
