import type { PluginClientContext } from "@getpaseo/plugin/client";
import { HostMonitorItem } from "./client/monitor";
import { SettingsScreen } from "./client/settings-screen";

export default function contribute(client: PluginClientContext) {
  // One 44 DP row above the sidebar's fixed tools; pressing it opens the
  // host-owned popover (a bottom sheet on compact layouts).
  const removeItem = client.addSidebarFooterItem({
    id: "host-resources",
    title: "宿主机资源",
    Component: HostMonitorItem,
  });
  // Settings → Plugins → 宿主机资源: host-scoped cadence and footer switch.
  const removeSettings = client.addSettingsScreen({
    id: "host-resources-settings",
    title: "宿主机资源",
    icon: "Activity",
    Component: SettingsScreen,
  });
  return () => {
    removeItem();
    removeSettings();
  };
}
