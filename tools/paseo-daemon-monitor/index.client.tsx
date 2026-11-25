import type { PluginClientContext } from "@getpaseo/plugin/client";
import { HostMonitorItem } from "./client/monitor";

export default function contribute(client: PluginClientContext) {
  // One row above the sidebar's fixed tools; pressing it opens the popover on wide
  // layouts and a bottom sheet on compact ones, both owned by the host.
  const removeItem = client.addSidebarFooterItem({
    id: "host-resources",
    title: "宿主机资源",
    Component: HostMonitorItem,
  });
  return () => {
    removeItem();
  };
}
