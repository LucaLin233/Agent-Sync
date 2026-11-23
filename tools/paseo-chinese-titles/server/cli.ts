import { spawn } from "node:child_process";
import type { ChineseTitlesSettings } from "../shared/settings";

export type CliFailure = "cli_missing" | "paseo_home_missing" | "timeout" | "failed" | "rejected";

export interface CliResult {
  ok: boolean;
  failure?: CliFailure;
  data?: unknown;
}

function minimalEnv(home: string): NodeJS.ProcessEnv {
  return {
    PATH: process.env.PATH ?? "",
    HOME: process.env.HOME ?? "",
    PASEO_HOME: home,
  };
}

/**
 * Runs the trusted official Paseo CLI with an argv array and the same daemon
 * home. The CLI owns the daemon connection and reads its own local credential;
 * this plugin never reads, parses or passes a credential.
 */
async function runPaseo(args: readonly string[], settings: ChineseTitlesSettings, timeoutMs = 20_000): Promise<CliResult> {
  const home = process.env.PASEO_HOME?.trim();
  if (!home) return { ok: false, failure: "paseo_home_missing" };
  const bin = settings.paseoBin.trim() || "paseo";
  return await new Promise<CliResult>((resolve) => {
    let settled = false;
    let stdout = "";
    const finish = (result: CliResult) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(result);
    };
    let child;
    try {
      child = spawn(bin, ["--home", home, ...args], {
        env: minimalEnv(home),
        stdio: ["ignore", "pipe", "pipe"],
      });
    } catch {
      resolve({ ok: false, failure: "cli_missing" });
      return;
    }
    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      finish({ ok: false, failure: "timeout" });
    }, timeoutMs);
    child.on("error", (error: NodeJS.ErrnoException) => {
      finish({ ok: false, failure: error.code === "ENOENT" ? "cli_missing" : "failed" });
    });
    child.stdout?.setEncoding("utf8");
    child.stderr?.setEncoding("utf8");
    child.stdout?.on("data", (chunk: string) => {
      if (stdout.length < 16_384) stdout += chunk;
    });
    // Drain stderr without keeping or logging it: provider or daemon details
    // must not enter plugin logs or state.
    child.stderr?.resume();
    child.on("close", (code) => {
      if (code !== 0) {
        finish({ ok: false, failure: "failed" });
        return;
      }
      const text = stdout.trim();
      if (!text) {
        finish({ ok: true });
        return;
      }
      let parsed: unknown;
      try {
        parsed = JSON.parse(text);
      } catch {
        finish({ ok: false, failure: "failed" });
        return;
      }
      if (parsed && typeof parsed === "object" && "error" in parsed && (parsed as { error?: unknown }).error) {
        finish({ ok: false, failure: "rejected" });
        return;
      }
      finish({ ok: true, data: parsed });
    });
  });
}

export function renameProjectViaCli(
  settings: ChineseTitlesSettings,
  projectId: string,
  name: string,
): Promise<CliResult> {
  return runPaseo(["project", "rename", projectId, name, "--json"], settings);
}

export function renameAgentViaCli(
  settings: ChineseTitlesSettings,
  agentId: string,
  title: string,
  timeoutMs = 20_000,
): Promise<CliResult> {
  return runPaseo(["agent", "update", agentId, "--name", title, "--json"], settings, timeoutMs);
}

function idsFrom(value: unknown, key: "projectId" | "id"): string[] | null {
  if (!Array.isArray(value)) return null;
  const ids: string[] = [];
  for (const entry of value) {
    if (!entry || typeof entry !== "object") return null;
    const id = (entry as Record<string, unknown>)[key];
    if (typeof id !== "string" || !id) return null;
    ids.push(id);
  }
  return ids;
}

export async function listProjectIdsViaCli(settings: ChineseTitlesSettings): Promise<string[] | null> {
  const result = await runPaseo(["project", "ls", "--json"], settings);
  return result.ok ? idsFrom(result.data, "projectId") : null;
}

export async function listWorkspaceIdsViaCli(settings: ChineseTitlesSettings): Promise<string[] | null> {
  const result = await runPaseo(["workspace", "ls", "--background", "--json"], settings);
  return result.ok ? idsFrom(result.data, "id") : null;
}

export async function listAgentIdsViaCli(settings: ChineseTitlesSettings): Promise<string[] | null> {
  const result = await runPaseo(["agent", "ls", "--all", "--json"], settings);
  return result.ok ? idsFrom(result.data, "id") : null;
}

export interface CliProject {
  projectId: string;
  name: string;
  path: string;
}

export async function listProjectsViaCli(settings: ChineseTitlesSettings): Promise<CliProject[] | null> {
  const result = await runPaseo(["project", "ls", "--json"], settings);
  if (!result.ok || !Array.isArray(result.data)) return null;
  const projects: CliProject[] = [];
  for (const entry of result.data) {
    if (!entry || typeof entry !== "object") return null;
    const record = entry as Record<string, unknown>;
    if (typeof record.projectId !== "string" || typeof record.name !== "string" || typeof record.path !== "string") return null;
    projects.push({ projectId: record.projectId, name: record.name, path: record.path });
  }
  return projects;
}

export async function createBootstrapWorkspaceViaCli(
  settings: ChineseTitlesSettings,
  projectId: string,
  directory: string,
  title: string,
): Promise<{ ok: boolean; workspaceId: string | null; failure?: CliFailure }> {
  const result = await runPaseo([
    "workspace",
    "create",
    "--isolation",
    "local",
    "--path",
    directory,
    "--project",
    projectId,
    "--title",
    title,
    "--background",
    "--json",
  ], settings);
  if (!result.ok) return { ok: false, workspaceId: null, failure: result.failure ?? "failed" };
  const record = result.data && typeof result.data === "object" ? result.data as Record<string, unknown> : null;
  return { ok: true, workspaceId: typeof record?.workspaceId === "string" ? record.workspaceId : null };
}
