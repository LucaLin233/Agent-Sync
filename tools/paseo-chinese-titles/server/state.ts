import { promises as fs } from "node:fs";
import { homedir } from "node:os";
import { isAbsolute, join, resolve, sep } from "node:path";

export type TitleStatus = "legacy" | "pending" | "generating" | "done" | "skipped" | "error";

export interface EntityTitleState {
  status: TitleStatus;
  title?: string;
  previousTitle?: string | null;
  at: string;
  error?: string;
}

export interface ChineseTitlesState {
  version: 1;
  initialized: boolean;
  installedAt: string;
  projects: Record<string, EntityTitleState>;
  workspaces: Record<string, EntityTitleState>;
  agents: Record<string, EntityTitleState>;
}

function pluginRoot(): string {
  const configured = process.env.PASEO_HOME?.trim();
  if (configured && !isAbsolute(configured)) throw new Error("PASEO_HOME must be absolute");
  return resolve(configured || join(homedir(), ".paseo"), "plugin-data", "paseo-chinese-titles");
}

/** Resolve a path and prove it stays inside this plugin's data directory. */
export function assertPluginPath(candidate: string): string {
  const root = pluginRoot();
  const resolved = resolve(candidate);
  if (resolved === root || resolved.startsWith(`${root}${sep}`)) return resolved;
  throw new Error("Plugin path escapes its data directory");
}

/** Build a path from fixed, separator-free segments only. */
export function safePluginPath(...segments: string[]): string {
  for (const segment of segments) {
    if (!segment || segment === "." || segment === ".." || segment.includes("/") || segment.includes("\\")) {
      throw new Error("Invalid plugin path segment");
    }
  }
  return assertPluginPath(join(pluginRoot(), ...segments));
}

export function pluginDataDir(): string {
  return assertPluginPath(pluginRoot());
}

export function helperDirectory(): string {
  return safePluginPath("helper");
}

export function isInsideDirectory(path: string | null | undefined, directory: string): boolean {
  if (!path) return false;
  const normalizedPath = resolve(path);
  const normalizedDirectory = resolve(directory);
  return normalizedPath === normalizedDirectory || normalizedPath.startsWith(`${normalizedDirectory}${sep}`);
}

export function newState(): ChineseTitlesState {
  return {
    version: 1,
    initialized: false,
    installedAt: new Date().toISOString(),
    projects: {},
    workspaces: {},
    agents: {},
  };
}

export async function loadState(): Promise<ChineseTitlesState> {
  const file = safePluginPath("state.json");
  try {
    const root = pluginDataDir();
    if (file !== root && !file.startsWith(`${root}${sep}`)) throw new Error("Invalid plugin state path");
    const raw = await fs.readFile(file, "utf8");
    const parsed = JSON.parse(raw) as Partial<ChineseTitlesState>;
    if (parsed?.version !== 1) return newState();
    return {
      version: 1,
      initialized: parsed.initialized === true,
      installedAt: typeof parsed.installedAt === "string" ? parsed.installedAt : new Date().toISOString(),
      projects: parsed.projects ?? {},
      workspaces: parsed.workspaces ?? {},
      agents: parsed.agents ?? {},
    };
  } catch {
    return newState();
  }
}

let writeChain: Promise<void> = Promise.resolve();

export function saveState(state: ChineseTitlesState): Promise<void> {
  const snapshot = JSON.stringify(state, null, 2);
  writeChain = writeChain.then(async () => {
    const dir = pluginDataDir();
    const root = pluginDataDir();
    if (dir !== root && !dir.startsWith(`${root}${sep}`)) throw new Error("Invalid plugin data directory");
    await fs.mkdir(dir, { recursive: true, mode: 0o700 });
    const file = safePluginPath("state.json");
    const temp = safePluginPath(`.state-${process.pid}-${Date.now()}.tmp`);
    if ((file !== dir && !file.startsWith(`${dir}${sep}`)) || (temp !== dir && !temp.startsWith(`${dir}${sep}`))) {
      throw new Error("Invalid plugin state path");
    }
    await fs.writeFile(temp, snapshot, { encoding: "utf8", mode: 0o600 });
    await fs.rename(temp, file);
  });
  return writeChain;
}

export function markBaseline(
  state: ChineseTitlesState,
  projects: readonly string[],
  workspaces: readonly string[],
  agents: readonly string[],
): boolean {
  if (state.initialized) return false;
  const now = new Date().toISOString();
  for (const id of projects) state.projects[id] ??= { status: "legacy", at: now };
  for (const id of workspaces) state.workspaces[id] ??= { status: "legacy", at: now };
  for (const id of agents) state.agents[id] ??= { status: "legacy", at: now };
  state.initialized = true;
  return true;
}
