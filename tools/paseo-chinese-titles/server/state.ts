import { promises as fs } from "node:fs";
import { homedir } from "node:os";
import { join, resolve, sep } from "node:path";

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

export function pluginDataDir(): string {
  const home = process.env.PASEO_HOME || join(homedir(), ".paseo");
  return join(home, "plugin-data", "paseo-chinese-titles");
}

export function helperDirectory(): string {
  return join(pluginDataDir(), "helper");
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
  const file = join(pluginDataDir(), "state.json");
  try {
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
    await fs.mkdir(dir, { recursive: true, mode: 0o700 });
    const file = join(dir, "state.json");
    const temp = join(dir, `.state-${process.pid}-${Date.now()}.tmp`);
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
