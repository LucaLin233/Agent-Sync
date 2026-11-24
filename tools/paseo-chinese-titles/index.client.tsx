import type { PluginClientContext } from "@getpaseo/plugin/client";
import { reconcileRpc } from "./shared/rpc";
import { ChineseTitlePanel } from "./client/regenerate";
import { ChineseTitlesSettingsScreen } from "./client/settings";
import { addChineseTitleHeaderButtons } from "./client/header-button";

const INTERVAL_MS = 20_000;

export default function contribute(client: PluginClientContext) {
  let stopped = false;
  const tick = () => {
    if (stopped) return;
    void client.rpc(reconcileRpc, {}).catch(() => undefined);
  };
  tick();
  const timer = setInterval(tick, INTERVAL_MS);
  const workspacePanel = client.addWorkspacePanel({
    id: "chinese-title",
    title: "中文标题",
    icon: "Languages",
    Component: ChineseTitlePanel,
  });
  const headerButtons = addChineseTitleHeaderButtons(client, (workspaceId) => {
    client.openPanel("chinese-title", { workspaceId });
  });
  const settingsScreen = client.addSettingsScreen({
    id: "chinese-titles",
    title: "Paseo 中文标题",
    icon: "Languages",
    Component: ChineseTitlesSettingsScreen,
  });
  return () => {
    stopped = true;
    clearInterval(timer);
    workspacePanel();
    settingsScreen();
    headerButtons();
  };
}
