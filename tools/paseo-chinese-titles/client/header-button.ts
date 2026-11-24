import type { PluginButtonRegistration, PluginClientContext } from "@getpaseo/plugin/client";

type WorkspaceHeaderHost = Pick<PluginClientContext, "paseo" | "addHeaderButton">;

interface HeaderWorkspace {
  id: string;
  archivingAt?: string | null;
}

/**
 * One header button per known workspace. In the compact iOS header Paseo puts each header button
 * into the workspace menu (`⋯`), so the row opens this plugin's existing workspace panel. One
 * workspace-list subscription keeps the registrations in step with new, archived, reconnected and
 * removed workspaces; there is no timer of its own.
 */
export function addChineseTitleHeaderButtons(
  client: WorkspaceHeaderHost,
  openPanel: (workspaceId: string) => void,
): () => void {
  const buttons = new Map<string, PluginButtonRegistration>();
  let stopped = false;
  let stop = () => {};

  const remove = (workspaceId: string) => {
    buttons.get(workspaceId)?.remove();
    buttons.delete(workspaceId);
  };
  const add = (workspace: HeaderWorkspace) => {
    const workspaceId = workspace.id.trim();
    if (stopped || !workspaceId) return;
    if (workspace.archivingAt) {
      remove(workspaceId);
      return;
    }
    if (buttons.has(workspaceId)) return;
    buttons.set(
      workspaceId,
      client.addHeaderButton({
        id: "chinese-title",
        workspaceId,
        button: {
          title: "中文标题",
          icon: "Languages",
          label: "中文标题",
          behavior: { kind: "action", onPress: () => openPanel(workspaceId) },
        },
      }),
    );
  };
  const reconcile = (workspaces: readonly HeaderWorkspace[]) => {
    const live = new Set<string>();
    for (const workspace of workspaces) {
      if (!workspace.archivingAt && workspace.id.trim()) live.add(workspace.id);
      add(workspace);
    }
    for (const workspaceId of [...buttons.keys()]) {
      if (!live.has(workspaceId)) remove(workspaceId);
    }
  };

  client.paseo.workspaces
    .list({ subscribe: {} })
    .then(({ subscription }) => {
      if (stopped) {
        void subscription.release();
        return;
      }
      const unsubscribe = subscription.subscribe({
        snapshot: (snapshot) => reconcile(snapshot.entries),
        update: (message) => {
          if (message.type !== "workspace_update") return;
          const update = message.payload;
          if (update.kind === "upsert") add(update.workspace);
          else remove(update.id);
        },
      });
      stop = () => {
        unsubscribe();
        void subscription.release();
      };
    })
    .catch((error: unknown) => {
      if (!stopped) {
        console.warn("Chinese title header button: workspace list unavailable", error);
      }
    });

  return () => {
    stopped = true;
    stop();
    for (const workspaceId of [...buttons.keys()]) remove(workspaceId);
  };
}
