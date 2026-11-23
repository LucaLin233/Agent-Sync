import type { PluginHandlerContext } from "@getpaseo/plugin/server";

/** The official plugin host API; this is the only Paseo type source in source files. */
export type PaseoApi = PluginHandlerContext["paseo"];
export type PaseoProject = Awaited<ReturnType<PaseoApi["projects"]["list"]>>["projects"][number];
export type PaseoWorkspace = Awaited<ReturnType<PaseoApi["workspaces"]["list"]>>["entries"][number];
export type PaseoAgent = Awaited<ReturnType<PaseoApi["agents"]["list"]>>["entries"][number]["agent"];
export type PaseoWorkspaceHandle = ReturnType<PaseoApi["workspaces"]["ref"]>;
export type PaseoAgentHandle = ReturnType<PaseoApi["agents"]["ref"]>;
