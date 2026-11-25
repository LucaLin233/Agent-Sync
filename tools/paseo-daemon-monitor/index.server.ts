import type { PluginServerContext } from "@getpaseo/plugin/server";
import { hostResourcesRpc } from "./shared/contract.ts";
import { monitorSettings } from "./shared/settings.ts";
import { applySettings, readHostResources, stopSampler } from "./server/sample.ts";

export default function contribute(server: PluginServerContext) {
  const settings = server.registerSettings(monitorSettings);

  const apply = (state: Awaited<ReturnType<typeof settings.read>>) => {
    if (state.status !== "ready") return;
    applySettings({ intervalMs: state.values.intervalMs });
  };

  // The loop adopts a new cadence in place; no reload is required.
  void settings.read().then(apply).catch(() => {});
  const unsubscribe = settings.subscribe((state) => apply(state));

  server.handle(hostResourcesRpc, readHostResources);
  return () => {
    unsubscribe();
    stopSampler();
  };
}
