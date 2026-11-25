import type { PluginServerContext } from "@getpaseo/plugin/server";
import { hostResourcesRpc } from "./shared/contract.ts";
import { readHostResources } from "./server/sample.ts";

export default function contribute(server: PluginServerContext) {
  server.handle(hostResourcesRpc, readHostResources);
  return () => {};
}
