import type { ChineseTitlesSettings } from "../shared/settings.ts";
import type { ConversationGenerationResult } from "./helper";
import type { PaseoAgent, PaseoApi } from "./paseo-types";
import type { ConversationExcerpt } from "../shared/transcript.ts";
import { selectableSessionsFor, resolveSessionSelection, isSelectableSession } from "../shared/session-options.ts";
import { truncateChars } from "../shared/title.ts";
import { helperDirectory, isInsideDirectory } from "./state.ts";

/** The daemon's regular plugin RPC transport allows 30 s in Paseo 0.17.3. */
const RPC_DEADLINE_MS = 22_000;
const GENERATION_DEADLINE_MS = 18_000;
/** Reserve time for the final read, setTitle/rename and verification. */
const WRITE_RESERVE_MS = 3_000;
/** Two writes plus two verifications need a little more than one. */
const DOUBLE_WRITE_RESERVE_MS = 4_500;

export type RegenerateStatus = "done" | "partial" | "busy" | "needs_selection" | "skipped" | "error";

/** Where the one generated summary is written. Omitted means the legacy workspace-only action. */
export type RegenerateScope = "both" | "workspace" | "session";

export interface RegenerateResult {
  status: RegenerateStatus;
  /** The summary title, present whenever the model returned one. */
  title?: string;
  reason?: string;
  workspaceUpdated: boolean;
  sessionUpdated: boolean;
  /** The session whose conversation was summarised; internal to the engine. */
  agentId?: string;
  /** Present only when some readable turns were not covered; `reason` names the limit. */
  coverage?: { kind: "partial"; reason?: string; turns: number };
}

export interface SessionRenameResult {
  ok: boolean;
  failure?: string;
}

export interface RegenerateOptions {
  paseo: PaseoApi;
  settings: ChineseTitlesSettings;
  workspaceId: string;
  /** Explicit user choice. Omitted only when the workspace has exactly one eligible session. */
  agentId?: string;
  /** Defaults to "workspace" so an older client keeps its previous behaviour. */
  scope?: RegenerateScope;
  /** Shared with the automatic first-task path so both cannot write at once. */
  claims: Set<string>;
  /** Shared with the automatic session path so a manual rename cannot race it. */
  agentClaims: Set<string>;
  generateConversation: (
    request: {
      transcript: string;
      segments?: readonly string[];
      projectName?: string | null;
      baseName?: string | null;
      projectId?: string | null;
      maxChars: number;
    },
    timeoutMs: number,
    deadlineAt: number,
  ) => Promise<ConversationGenerationResult>;
  listAgents: () => Promise<PaseoAgent[]>;
  readConversation: (agentId: string) => Promise<ConversationExcerpt | null>;
  /** Official CLI rename for one session; the caller owns credential use. */
  renameSession: (agentId: string, title: string, timeoutMs: number) => Promise<SessionRenameResult>;
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

function statusFor(wantsWorkspace: boolean, wantsSession: boolean, workspaceUpdated: boolean, sessionUpdated: boolean): RegenerateStatus {
  const updated = (wantsWorkspace ? 1 : 0) * Number(workspaceUpdated) + (wantsSession ? 1 : 0) * Number(sessionUpdated);
  const requested = Number(wantsWorkspace) + Number(wantsSession);
  if (updated === requested) return "done";
  return updated > 0 ? "partial" : "error";
}

/**
 * Regenerates one workspace's and/or one session's display title from the
 * conversation the user picked. The summary describes what the session
 * actually discussed, so a later topic change is reflected rather than the
 * first request being repeated.
 *
 * There is no deterministic substitute for a conversation summary: if the
 * model is unavailable, times out or answers without a valid Chinese title,
 * the existing titles are kept. One generated title is reused for both
 * requested targets. A short conversation needs one model turn; a long one is
 * condensed part by part first, all inside the same request's deadline.
 *
 * Paseo 0.17.3's PluginHandlerContext has no abort signal. The caller therefore
 * gives this function a deadline shorter than the daemon's 30 s RPC timeout,
 * and this function checks that deadline immediately before each write. A late
 * model completion can never write after the RPC has timed out.
 */
export async function regenerateWorkspaceTitle(options: RegenerateOptions): Promise<RegenerateResult> {
  const coverageOut: { value?: RegenerateResult["coverage"] } = {};
  const result = await runRegeneration(options, coverageOut);
  const wrote = result.status === "done" || result.status === "partial";
  return coverageOut.value && wrote ? { ...result, coverage: coverageOut.value } : result;
}

async function runRegeneration(
  options: RegenerateOptions,
  coverageOut: { value?: RegenerateResult["coverage"] },
): Promise<RegenerateResult> {
  const scope: RegenerateScope = options.scope ?? "workspace";
  const wantsWorkspace = scope !== "session";
  const wantsSession = scope !== "workspace";
  const { paseo, workspaceId, claims } = options;
  const now = options.now ?? Date.now;
  const deadlineAt = options.deadlineAt ?? now() + RPC_DEADLINE_MS;
  const reserve = wantsWorkspace && wantsSession ? DOUBLE_WRITE_RESERVE_MS : WRITE_RESERVE_MS;

  if (wantsWorkspace && claims.has(workspaceId)) {
    return { status: "busy", workspaceUpdated: false, sessionUpdated: false };
  }
  if (wantsWorkspace) claims.add(workspaceId);
  let claimedAgentId: string | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  try {
    const workspace = await paseo.workspaces.ref(workspaceId).refresh();
    if (!workspace || workspace.archivingAt) {
      return { status: "skipped", reason: "not_found", workspaceUpdated: false, sessionUpdated: false };
    }
    if (workspace.background || isInsideDirectory(workspace.workspaceDirectory, helperDirectory())) {
      return { status: "skipped", reason: "excluded", workspaceUpdated: false, sessionUpdated: false };
    }

    const agents = (await options.listAgents()).filter(
      (agent) => agent.workspaceId === workspace.id && !isExcludedAgent(agent),
    );
    const selected = options.agentId
      ? agents.find((agent) => agent.id === options.agentId)
      : undefined;
    if (options.agentId && !selected) {
      return { status: "skipped", reason: "session_not_selectable", workspaceUpdated: false, sessionUpdated: false };
    }

    const sessions = selectableSessionsFor(agents, workspace.id);
    const agentId = resolveSessionSelection(sessions, selected?.id);
    if (!agentId) {
      return {
        status: "needs_selection",
        reason: sessions.length ? "choose_session" : "no_session",
        workspaceUpdated: false,
        sessionUpdated: false,
      };
    }
    const targetAgent = agents.find((agent) => agent.id === agentId);
    if (!targetAgent) {
      return { status: "skipped", reason: "session_not_selectable", workspaceUpdated: false, sessionUpdated: false };
    }

    // The manual session write shares the automatic path's claim so the two
    // cannot rename the same session concurrently in this process.
    if (wantsSession) {
      if (options.agentClaims.has(agentId)) {
        return { status: "busy", agentId, workspaceUpdated: false, sessionUpdated: false };
      }
      options.agentClaims.add(agentId);
      claimedAgentId = agentId;
    }

    // Reading the chosen session is bounded, but it still spends the shared RPC
    // budget; re-check the deadline before the model is even started.
    if (now() >= deadlineAt - reserve) {
      return { status: "error", reason: "timeout", workspaceUpdated: false, sessionUpdated: false };
    }
    const conversation = await options.readConversation(agentId);
    if (conversation === null) {
      return { status: "skipped", reason: "conversation_unavailable", agentId, workspaceUpdated: false, sessionUpdated: false };
    }
    const transcript = conversation.text.trim();
    if (!transcript) {
      return { status: "skipped", reason: "empty_conversation", agentId, workspaceUpdated: false, sessionUpdated: false };
    }

    // A summary built from a bounded read of a longer or partly unreadable
    // session is still useful, but the caller must be able to say that some
    // turns were not covered instead of presenting it as complete.
    // Only an incomplete read is reported; a full read needs no caveat.
    const coverage = conversation.coverage ?? { kind: "full" as const };
    if (coverage.kind === "partial") {
      coverageOut.value = {
        kind: "partial",
        turns: conversation.coveredTurns ?? conversation.turns,
        ...(coverage.reason ? { reason: coverage.reason } : {}),
      };
    }
    const startWorkspaceTitle = normalizedTitle(workspace.title);
    const startSessionTitle = normalizedTitle(targetAgent.title);
    const maxChars = options.settings.titleMaxChars;
    const remaining = deadlineAt - now() - reserve;
    if (remaining <= 0) {
      return { status: "error", reason: "timeout", agentId, workspaceUpdated: false, sessionUpdated: false };
    }
    const generationBudget = Math.min(
      options.generationTimeoutMs ?? GENERATION_DEADLINE_MS,
      remaining,
    );
    const generation: Promise<ConversationGenerationResult | null> = options.generateConversation({
      transcript,
      ...(conversation.segments && conversation.segments.length > 1 ? { segments: conversation.segments } : {}),
      projectName: workspace.projectDisplayName,
      baseName: workspace.name,
      projectId: workspace.projectId,
      maxChars,
    }, generationBudget, deadlineAt - reserve).catch(() => null);
    const timeout = new Promise<null>((resolve) => {
      timer = setTimeout(() => resolve(null), Math.max(0, deadlineAt - now()));
    });
    const generated = await Promise.race([generation, timeout]);
    if (!generated) {
      return { status: "error", reason: "timeout", agentId, workspaceUpdated: false, sessionUpdated: false };
    }
    if (now() >= deadlineAt - reserve) {
      return { status: "error", reason: "timeout", agentId, workspaceUpdated: false, sessionUpdated: false };
    }
    if (!generated.title) {
      return {
        status: "error",
        reason: generated.errorCode ?? "model_failed",
        agentId,
        workspaceUpdated: false,
        sessionUpdated: false,
      };
    }

    // The model output was already validated and truncated as a Chinese title
    // by the generator. Both targets reuse this exact one summary, so the
    // success message always names the value actually written to each target.
    const summary = truncateChars(generated.title, maxChars);

    // Re-read every target before the first write: a manual rename that landed
    // while the model was running must win, and no target is touched then.
    if (wantsWorkspace) {
      const current = await paseo.workspaces.ref(workspaceId).refresh();
      if (!current || current.archivingAt) {
        return { status: "skipped", reason: "not_found", agentId, workspaceUpdated: false, sessionUpdated: false };
      }
      if (normalizedTitle(current.title) !== startWorkspaceTitle) {
        return { status: "skipped", reason: "manual_change", agentId, workspaceUpdated: false, sessionUpdated: false };
      }
    }
    if (wantsSession) {
      const refreshed = await paseo.agents.ref(agentId).refresh();
      const current = refreshed?.agent;
      if (!current) {
        return { status: "skipped", reason: "session_not_found", agentId, workspaceUpdated: false, sessionUpdated: false };
      }
      if (current.archivedAt) {
        return { status: "skipped", reason: "session_archived", agentId, workspaceUpdated: false, sessionUpdated: false };
      }
      if (current.workspaceId !== workspaceId) {
        return { status: "skipped", reason: "session_moved", agentId, workspaceUpdated: false, sessionUpdated: false };
      }
      if (normalizedTitle(current.title) !== startSessionTitle) {
        return { status: "skipped", reason: "session_manual_change", agentId, workspaceUpdated: false, sessionUpdated: false };
      }
    }
    if (now() >= deadlineAt - reserve) {
      return { status: "error", reason: "timeout", agentId, workspaceUpdated: false, sessionUpdated: false };
    }

    // The two writes are independent; there is no cross-object transaction.
    // Each one reports its own verified outcome so a partial result is visible.
    let workspaceUpdated = false;
    let sessionUpdated = false;
    let reason: string | undefined;
    // A target that changed under us was skipped, not failed; with nothing
    // written and no write failure the request reports "skipped". A real write
    // failure is never downgraded to a skip.
    let skipped = false;
    let writeFailed = false;

    if (wantsWorkspace) {
      if (now() >= deadlineAt - WRITE_RESERVE_MS) {
        reason = "timeout";
      } else {
        try {
          await paseo.workspaces.ref(workspaceId).setTitle(summary);
        } catch {
          reason = "workspace_write_failed";
          writeFailed = true;
        }
        const verified = await paseo.workspaces.ref(workspaceId).refresh().catch(() => null);
        if (verified && normalizedTitle(verified.title) === summary) {
          workspaceUpdated = true;
        } else if (!writeFailed) {
          reason = "workspace_verification_failed";
          writeFailed = true;
        }
      }
    }

    if (wantsSession) {
      // The workspace write above is a separate object. Re-read the session
      // immediately before the CLI so a manual rename, archive or move that
      // landed in between is never overwritten; the workspace write already
      // happened and is reported as a verified partial result.
      const latest = await paseo.agents.ref(agentId).refresh().catch(() => null);
      const latestAgent = latest?.agent;
      if (!latestAgent || latestAgent.archivedAt || latestAgent.workspaceId !== workspaceId ||
        normalizedTitle(latestAgent.title) !== startSessionTitle) {
        skipped = true;
        reason ??= !latestAgent
          ? "session_not_found"
          : latestAgent.archivedAt
            ? "session_archived"
            : latestAgent.workspaceId !== workspaceId
              ? "session_moved"
              : "session_manual_change";
      } else if (now() >= deadlineAt - 1_000) {
        reason ??= "timeout";
      } else {
        const renameBudget = Math.max(1_000, deadlineAt - now() - 1_000);
        let renamed: SessionRenameResult = { ok: false, failure: "failed" };
        try {
          renamed = await options.renameSession(agentId, summary, renameBudget);
        } catch {
          renamed = { ok: false, failure: "failed" };
        }
        const verified = await paseo.agents.ref(agentId).refresh().catch(() => null);
        if (verified?.agent && normalizedTitle(verified.agent.title) === summary) {
          sessionUpdated = true;
        } else if (!renamed.ok) {
          reason ??= "session_write_failed";
          writeFailed = true;
        } else {
          reason ??= "session_verification_failed";
          writeFailed = true;
        }
      }
    }

    const written = statusFor(wantsWorkspace, wantsSession, workspaceUpdated, sessionUpdated);
    const status: RegenerateStatus = skipped && !writeFailed && written === "error" ? "skipped" : written;
    if (status === "done") reason = undefined;
    return {
      status,
      title: summary,
      ...(reason ? { reason } : {}),
      workspaceUpdated,
      sessionUpdated,
      agentId,
    };
  } catch {
    return { status: "error", reason: "internal_failed", workspaceUpdated: false, sessionUpdated: false };
  } finally {
    if (timer) clearTimeout(timer);
    if (claimedAgentId) options.agentClaims.delete(claimedAgentId);
    if (wantsWorkspace) claims.delete(workspaceId);
  }
}

export { RPC_DEADLINE_MS };
