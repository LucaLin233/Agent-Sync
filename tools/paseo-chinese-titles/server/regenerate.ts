import type { ChineseTitlesSettings } from "../shared/settings";
import type { GenerationRequest, GenerationResult } from "./helper";
import type { PaseoAgent, PaseoApi, PaseoWorkspace } from "./paseo-types";
import { pickFirstTask, type FirstTaskFact } from "../shared/first-task.ts";
import { distinctWorkspaceTitle, fallbackTaskTitle, hasHan, isAcceptableTitle, truncateChars } from "../shared/title.ts";
import { helperDirectory, isInsideDirectory } from "./state.ts";

/** The daemon's regular plugin RPC transport allows 30 s in Paseo 0.17.3. */
const RPC_DEADLINE_MS = 22_000;
const GENERATION_DEADLINE_MS = 18_000;
/** Reserve time for the final read, setTitle and verification. */
const WRITE_RESERVE_MS = 3_000;

export interface FirstPrompt {
  text: string;
  turnId: string | null;
  at: string;
}

export type RegenerateStatus = "done" | "busy" | "skipped" | "error";

export interface RegenerateResult {
  status: RegenerateStatus;
  title?: string;
  reason?: string;
}

export interface RegenerateOptions {
  paseo: PaseoApi;
  settings: ChineseTitlesSettings;
  workspaceId: string;
  /** Shared with the automatic first-task path so both cannot write at once. */
  claims: Set<string>;
  generate: (request: GenerationRequest, timeoutMs: number, deadlineAt: number) => Promise<GenerationResult>;
  listAgents: () => Promise<PaseoAgent[]>;
  readFirstPrompt: (agentId: string) => Promise<FirstPrompt | null>;
  /** Absolute epoch milliseconds; defaults to now + 22 s. */
  deadlineAt?: number;
  now?: () => number;
  generationTimeoutMs?: number;
}

function normalizedTitle(value: string | null | undefined): string | null {
  const title = value?.trim();
  return title ? title : null;
}

function isExcludedAgent(agent: PaseoAgent): boolean {
  const parent = agent.labels?.["paseo.parent-agent-id"];
  return Boolean(parent) || agent.background === true || isInsideDirectory(agent.cwd, helperDirectory());
}

async function firstTaskForWorkspace(
  options: RegenerateOptions,
  workspace: PaseoWorkspace,
): Promise<FirstPrompt | null> {
  const agents = (await options.listAgents()).filter(
    (agent) => agent.workspaceId === workspace.id && !isExcludedAgent(agent),
  );
  const facts: FirstTaskFact[] = [];
  for (const agent of agents) {
    if (!agent.lastUserMessageAt) continue;
    const prompt = await options.readFirstPrompt(agent.id);
    if (prompt) facts.push({ id: agent.id, ...prompt });
  }
  return pickFirstTask(facts);
}

function usableTitle(title: string, prompt: string, maxChars: number): string {
  const value = distinctWorkspaceTitle(title, prompt, maxChars);
  if (isAcceptableTitle(value)) return value;
  return distinctWorkspaceTitle(
    fallbackTaskTitle({ prompt, maxChars }),
    prompt,
    maxChars,
  );
}

/**
 * Regenerates one workspace's display title. It never changes directories,
 * branches or agent titles, and it is independent of the automatic baseline
 * (legacy/done/skipped) and of autoNameWorkspaces, so the workspace button can
 * be pressed again after any earlier result.
 *
 * Paseo 0.17.3's PluginHandlerContext has no abort signal. The caller therefore
 * gives this function a deadline shorter than the daemon's 30 s RPC timeout,
 * and this function checks that deadline immediately before writing. A late
 * model or helper completion can never write after the RPC has timed out.
 */
export async function regenerateWorkspaceTitle(options: RegenerateOptions): Promise<RegenerateResult> {
  const { paseo, workspaceId, claims } = options;
  if (claims.has(workspaceId)) return { status: "busy" };
  claims.add(workspaceId);
  const now = options.now ?? Date.now;
  const deadlineAt = options.deadlineAt ?? now() + RPC_DEADLINE_MS;
  let timer: ReturnType<typeof setTimeout> | null = null;
  try {
    const workspace = await paseo.workspaces.ref(workspaceId).refresh();
    if (!workspace || workspace.archivingAt) return { status: "skipped", reason: "not_found" };
    if (workspace.background || isInsideDirectory(workspace.workspaceDirectory, helperDirectory())) {
      return { status: "skipped", reason: "excluded" };
    }

    const startTitle = normalizedTitle(workspace.title);
    const first = await firstTaskForWorkspace(options, workspace);
    const prompt = first?.text
      ?? (startTitle && hasHan(startTitle) ? startTitle : "");
    const maxChars = options.settings.titleMaxChars;
    const request: GenerationRequest = {
      kind: "workspace",
      prompt,
      projectName: workspace.projectDisplayName,
      baseName: workspace.name,
      projectId: workspace.projectId,
      maxChars,
    };

    const remaining = deadlineAt - now() - WRITE_RESERVE_MS;
    if (remaining <= 0) return { status: "error", reason: "timeout" };
    const generationBudget = Math.min(
      options.generationTimeoutMs ?? GENERATION_DEADLINE_MS,
      remaining,
    );
    const generation = options.generate(request, generationBudget, deadlineAt - WRITE_RESERVE_MS).catch(() => null);
    const timeout = new Promise<null>((resolve) => {
      timer = setTimeout(() => resolve(null), Math.max(0, deadlineAt - now()));
    });
    const generated = await Promise.race([generation, timeout]);
    if (!generated) return { status: "error", reason: "timeout" };
    if (now() >= deadlineAt - WRITE_RESERVE_MS) return { status: "error", reason: "timeout" };

    const current = await paseo.workspaces.ref(workspaceId).refresh();
    if (!current || current.archivingAt) return { status: "skipped", reason: "not_found" };
    if (now() >= deadlineAt - WRITE_RESERVE_MS) return { status: "error", reason: "timeout" };
    if (normalizedTitle(current.title) !== startTitle) {
      return { status: "skipped", reason: "manual_change" };
    }

    const title = usableTitle(generated.title, prompt, maxChars);
    await paseo.workspaces.ref(workspaceId).setTitle(title);
    const verified = await paseo.workspaces.ref(workspaceId).refresh();
    if (normalizedTitle(verified?.title) !== title) {
      return { status: "error", reason: "verification_failed" };
    }
    return { status: "done", title: truncateChars(title, maxChars) };
  } catch {
    return { status: "error", reason: "internal_failed" };
  } finally {
    if (timer) clearTimeout(timer);
    claims.delete(workspaceId);
  }
}

export { RPC_DEADLINE_MS };
