import type { ChineseTitlesSettings } from "../shared/settings.ts";
import type { ConversationGenerationResult } from "./helper";
import type { PaseoAgent, PaseoApi } from "./paseo-types";
import type { ConversationExcerpt } from "../shared/transcript.ts";
import { selectableSessionsFor, resolveSessionSelection, isSelectableSession } from "../shared/session-options.ts";
import { distinctWorkspaceTitle, truncateChars } from "../shared/title.ts";
import { helperDirectory, isInsideDirectory } from "./state.ts";

/** The daemon's regular plugin RPC transport allows 30 s in Paseo 0.17.3. */
const RPC_DEADLINE_MS = 22_000;
const GENERATION_DEADLINE_MS = 18_000;
/** Reserve time for the final read, setTitle and verification. */
const WRITE_RESERVE_MS = 3_000;

export type RegenerateStatus = "done" | "busy" | "needs_selection" | "skipped" | "error";

export interface RegenerateResult {
  status: RegenerateStatus;
  title?: string;
  reason?: string;
}

export interface RegenerateOptions {
  paseo: PaseoApi;
  settings: ChineseTitlesSettings;
  workspaceId: string;
  /** Explicit user choice. Omitted only when the workspace has exactly one eligible session. */
  agentId?: string;
  /** Shared with the automatic first-task path so both cannot write at once. */
  claims: Set<string>;
  generateConversation: (
    request: { transcript: string; projectName?: string | null; baseName?: string | null; projectId?: string | null; maxChars: number },
    timeoutMs: number,
    deadlineAt: number,
  ) => Promise<ConversationGenerationResult>;
  listAgents: () => Promise<PaseoAgent[]>;
  readConversation: (agentId: string) => Promise<ConversationExcerpt | null>;
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
  return !isSelectableSession({
    id: agent.id,
    workspaceId: agent.workspaceId,
    background: agent.background,
    internal: agent.internal,
    archivedAt: agent.archivedAt,
    labels: agent.labels,
    metadata: agent.metadata,
  }) || isInsideDirectory(agent.cwd, helperDirectory());
}

/**
 * Regenerates one workspace's display title from the conversation the user
 * picked. The summary describes what the session actually discussed, so a
 * later topic change is reflected rather than the first request being repeated.
 *
 * There is no deterministic substitute for a conversation summary: if the
 * model is unavailable, times out or answers without a valid Chinese title,
 * the existing workspace title is kept and the UI offers a retry.
 *
 * Paseo 0.17.3's PluginHandlerContext has no abort signal. The caller therefore
 * gives this function a deadline shorter than the daemon's 30 s RPC timeout,
 * and this function checks that deadline immediately before writing. A late
 * model completion can never write after the RPC has timed out.
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

    const agents = (await options.listAgents()).filter(
      (agent) => agent.workspaceId === workspace.id && !isExcludedAgent(agent),
    );
    const selected = options.agentId
      ? agents.find((agent) => agent.id === options.agentId)
      : undefined;
    if (options.agentId && !selected) return { status: "skipped", reason: "session_not_selectable" };

    const sessions = selectableSessionsFor(agents, workspace.id);
    const agentId = resolveSessionSelection(sessions, selected?.id);
    if (!agentId) return { status: "needs_selection", reason: sessions.length ? "choose_session" : "no_session" };

    // Reading the chosen session is bounded, but it still spends the shared RPC
    // budget; re-check the deadline before the model is even started.
    if (now() >= deadlineAt - WRITE_RESERVE_MS) return { status: "error", reason: "timeout" };
    const conversation = await options.readConversation(agentId);
    if (conversation === null) return { status: "skipped", reason: "conversation_unavailable" };
    const transcript = conversation.text.trim();
    if (!transcript) return { status: "skipped", reason: "empty_conversation" };

    const startTitle = normalizedTitle(workspace.title);
    const maxChars = options.settings.titleMaxChars;
    const remaining = deadlineAt - now() - WRITE_RESERVE_MS;
    if (remaining <= 0) return { status: "error", reason: "timeout" };
    const generationBudget = Math.min(
      options.generationTimeoutMs ?? GENERATION_DEADLINE_MS,
      remaining,
    );
    const generation: Promise<ConversationGenerationResult | null> = options.generateConversation({
      transcript,
      projectName: workspace.projectDisplayName,
      baseName: workspace.name,
      projectId: workspace.projectId,
      maxChars,
    }, generationBudget, deadlineAt - WRITE_RESERVE_MS).catch(() => null);
    const timeout = new Promise<null>((resolve) => {
      timer = setTimeout(() => resolve(null), Math.max(0, deadlineAt - now()));
    });
    const generated = await Promise.race([generation, timeout]);
    if (!generated) return { status: "error", reason: "timeout" };
    if (now() >= deadlineAt - WRITE_RESERVE_MS) return { status: "error", reason: "timeout" };
    if (!generated.title) return { status: "error", reason: generated.errorCode ?? "model_failed" };

    const current = await paseo.workspaces.ref(workspaceId).refresh();
    if (!current || current.archivingAt) return { status: "skipped", reason: "not_found" };
    if (now() >= deadlineAt - WRITE_RESERVE_MS) return { status: "error", reason: "timeout" };
    if (normalizedTitle(current.title) !== startTitle) {
      return { status: "skipped", reason: "manual_change" };
    }

    // The model output was already validated as a Chinese title; keep it
    // distinct from Paseo's native first-prompt title so the daemon's
    // built-in auto-name cannot replace it later.
    const title = distinctWorkspaceTitle(generated.title, "", maxChars);
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
