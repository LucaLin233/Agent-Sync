import test from "node:test";
import assert from "node:assert/strict";
import { addChineseTitleHeaderButtons } from "../client/header-button.ts";

// Mirrors @getpaseo/client's owned-subscription contract (0.16.0 and 0.17.3 are identical here):
// subscribe() delivers the snapshot synchronously, then replays buffered updates in order.
function fake({ snapshotEntries, bufferedUpdates = [], snapshotOnSubscribe = true, snapshotOnly = false }) {
  const live = new Map();
  const opened = [];
  let observer = null;
  let released = 0;
  let unsubscribed = 0;
  let resolveList;
  const listed = new Promise((resolve) => (resolveList = resolve));
  const client = {
    addHeaderButton(input) {
      if (live.has(input.workspaceId)) throw new Error(`duplicate header button for ${input.workspaceId}`);
      live.set(input.workspaceId, input.button);
      return { update() {}, remove: () => void live.delete(input.workspaceId) };
    },
    paseo: {
      workspaces: {
        list: async () => {
          await listed;
          return {
            entries: snapshotEntries,
            subscription: {
              subscribe(next) {
                observer = next;
                if (snapshotOnly) return () => {};
                if (snapshotOnSubscribe) {
                  next.snapshot({ entries: snapshotEntries, subscriptionId: "s1" });
                  for (const update of bufferedUpdates) next.update(update);
                }
                return () => {
                  unsubscribed += 1;
                  observer = null;
                };
              },
              release: async () => {
                released += 1;
              },
            },
          };
        },
      },
    },
  };
  return {
    client,
    live,
    opened,
    settle: async () => {
      resolveList();
      await new Promise((resolve) => setTimeout(resolve, 0));
    },
    get observer() {
      return observer;
    },
    counters: () => ({ released, unsubscribed }),
  };
}

const upsert = (id, extra = {}) => ({
  type: "workspace_update",
  payload: { kind: "upsert", workspace: { id, ...extra } },
});
const removal = (id) => ({ type: "workspace_update", payload: { kind: "remove", id } });

test("registers live workspaces from the snapshot and opens the existing panel", async () => {
  const f = fake({
    snapshotEntries: [{ id: "ws-1" }, { id: "ws-archiving", archivingAt: "2026-11-24T00:00:00.000Z" }],
  });
  addChineseTitleHeaderButtons(f.client, (id) => f.opened.push(id));
  await f.settle();
  assert.deepEqual([...f.live.keys()], ["ws-1"]);
  const button = f.live.get("ws-1");
  assert.equal(button.title, "中文标题");
  assert.equal(button.icon, "Languages");
  assert.equal(button.behavior.kind, "action");
  button.behavior.onPress();
  assert.deepEqual(f.opened, ["ws-1"]);
});

test("a buffered removal replayed after the synchronous snapshot is not undone", async () => {
  const f = fake({
    snapshotEntries: [{ id: "ws-1" }],
    bufferedUpdates: [removal("ws-1"), upsert("ws-9")],
  });
  addChineseTitleHeaderButtons(f.client, () => {});
  await f.settle();
  assert.deepEqual([...f.live.keys()], ["ws-9"]);
});

test("a buffered archive upsert replayed after the synchronous snapshot stays hidden", async () => {
  const f = fake({
    snapshotEntries: [{ id: "ws-1" }],
    bufferedUpdates: [upsert("ws-1", { archivingAt: "2026-11-24T00:00:00.000Z" })],
  });
  addChineseTitleHeaderButtons(f.client, () => {});
  await f.settle();
  assert.equal(f.live.size, 0);
});

test("follows live upserts, archive, removal, a reconnect snapshot and cleanup", async () => {
  const f = fake({ snapshotEntries: [{ id: "ws-1" }] });
  const cleanup = addChineseTitleHeaderButtons(f.client, () => {});
  await f.settle();
  f.observer.update(upsert("ws-2"));
  assert.deepEqual([...f.live.keys()].sort(), ["ws-1", "ws-2"]);
  f.observer.update(upsert("ws-2"));
  assert.equal(f.live.size, 2);
  f.observer.update(upsert("ws-2", { archivingAt: "2026-11-24T00:00:00.000Z" }));
  assert.deepEqual([...f.live.keys()], ["ws-1"]);
  f.observer.update(removal("ws-1"));
  assert.equal(f.live.size, 0);
  f.observer.snapshot({ entries: [{ id: "ws-3" }], subscriptionId: "s2" });
  assert.deepEqual([...f.live.keys()], ["ws-3"]);
  cleanup();
  assert.equal(f.live.size, 0);
  assert.deepEqual(f.counters(), { released: 1, unsubscribed: 1 });
});

test("a later snapshot replaces stale buttons instead of keeping them", async () => {
  const f = fake({ snapshotEntries: [{ id: "ws-1" }], snapshotOnSubscribe: false });
  addChineseTitleHeaderButtons(f.client, () => {});
  await f.settle();
  assert.equal(f.live.size, 0);
  f.observer.snapshot({ entries: [{ id: "ws-4" }], subscriptionId: "s9" });
  assert.deepEqual([...f.live.keys()], ["ws-4"]);
});

test("releases the subscription when the plugin stops before it resolves", async () => {
  const f = fake({ snapshotEntries: [{ id: "ws-1" }], snapshotOnly: true });
  const cleanup = addChineseTitleHeaderButtons(f.client, () => {});
  cleanup();
  await f.settle();
  assert.equal(f.live.size, 0);
  assert.deepEqual(f.counters(), { released: 1, unsubscribed: 0 });
});
