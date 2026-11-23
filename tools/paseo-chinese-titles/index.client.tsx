import type { PluginClientContext } from "@getpaseo/plugin/client";
import { reconcileRpc } from "./shared/rpc";
import { ChineseTitlesSettingsScreen } from "./client/settings";

const INTERVAL_MS = 20_000;

export default function contribute(client: PluginClientContext) {
  let stopped = false;
  const tick = () => {
    if (stopped) return;
    void client.rpc(reconcileRpc, {}).catch(() => undefined);
  };
  tick();
  const timer = setInterval(tick, INTERVAL_MS);
  const settingsScreen = client.addSettingsScreen({
    id: "chinese-titles",
    title: "Paseo 中文标题",
    icon: "Languages",
    Component: ChineseTitlesSettingsScreen,
  });
  return () => {
    stopped = true;
    clearInterval(timer);
    settingsScreen();
  };
}
