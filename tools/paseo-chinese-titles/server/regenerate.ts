import type { ChineseTitlesSettings } from "../shared/settings.ts";
import type { ConversationGenerationResult } from "./helper";
import type { PaseoAgent, PaseoApi } from "./paseo-types";
import type { ConversationExcerpt } from "../shared/transcript.ts";
import { selectableSessionsFor, resolveSessionSelection, isSelectableSession } from "../shared/session-options.ts";
import { truncateChars } from "../shared/title.ts";
import { helperDirectory, isInsideDirectory } from "./state.ts";

/**
 * A manual regeneration runs in the plugin's background job, not inside the
 * daemon's 30 s plugin RPC transport. The panel starts the job, receives an id
 * immediately and reads its state. This deadline therefore bounds the task
 * itself: a long conversation may condense several parts and still write.
 */
const MANUAL_GENERATION_DEADLINE_MS = 120_000;
/** One model step (a digest or the final title) gets its own bounded share. */
const GENERATION_DEADLINE_MS = 35_000;
/** Reserve time for the final read, setTitle/rename and verification. */
const WRITE_RESERVE_MS = 6_000;
/** Two writes plus two verifications need a little more than one. */
const DOUBLE_WRITE_RESERVE_MS = 9_000;

export type RegenerateStatus = "done" | "partial" | "busy" | "needs_selection" | "skipped" | "error";

/** Where the one generated summary is written. Omitted means the legacy workspace-only action. */
export type RegenerateScope = "both" | "workspace" | "session";

/**
 * Which step the run reached when it failed. Set on a mutable object owned by
 * the background job, so a failure keeps its stage even where the returned
 * result carries no `agentId` (an early deadline check, a thrown error). It is
 * internal diagnostics only: no RPC field, no text, no request id.
 */
export type RegenerationStage =
  | "workspace_read"
  | "agent_list"
  | "session_select"
  | "conversation_read"
  | "model_generation"
  | "write_preflight"
  | "workspace_write"
  | "session_write"
  | "state_save";

/**
 * Which clock stopped a timeout: the task deadline this run measured, the
 * session CLI's own budget, or one of the helper's own clocks (which one is
 * decided inside helper.ts and passed through). A controlled value only; no
 * provider, CLI or exception text is ever stored.
 */
export type TimeoutSource =
  | "task_deadline"
  | "cli"
  /** A helper timeout with no metadata: the generic bucket kept for older runs. */
  | "helper"
  | "helper_start_deadline"
  | "helper_turn_deadline"
  | "helper_turn_cap"
  | "helper_sdk_timeout";

export interface RegenerationDiagnostics {
  stage?: RegenerationStage;
  /** The selected Paseo session, recorded as soon as selection resolves. */
  agentId?: string;
  /** Measured ms a failing timeout compared against; only ever set by a timeout. */
  budgetMs?: number;
  /** Which clock timed out; only ever set by a timeout. */
  timeoutSource?: TimeoutSource;
}

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
  /** Absolute epoch milliseconds; defaults to now + the manual job deadline. */
  deadlineAt?: number;
  now?: () => number;
  generationTimeoutMs?: number;
  /**
   * Checked immediately before every write. The plugin sets it when the plugin
   * is disposed or reloaded, so work that outlived its job never writes late.
   */
  isCancelled?: () => boolean;
  /** Internal failure context for the job's one diagnostic line; never returned. */
  diagnostics?: RegenerationDiagnostics;
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
 * The manual panel runs this as a background job instead of one long RPC, so
 * the deadline is the job's own budget rather than the daemon's 30 s plugin
 * transport. The check immediately before each write, plus the caller's
 * cancellation probe, keeps a late model answer from writing after the job was
 * abandoned, reloaded or replaced.
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
  const deadlineAt = options.deadlineAt ?? now() + MANUAL_GENERATION_DEADLINE_MS;
  const cancelled = options.isCancelled ?? (() => false);
  const reserve = wantsWorkspace && wantsSession ? DOUBLE_WRITE_RESERVE_MS : WRITE_RESERVE_MS;

  if (wantsWorkspace && claims.has(workspaceId)) {
    return { status: "busy", workspaceUpdated: false, sessionUpdated: false };
  }
  if (wantsWorkspace) claims.add(workspaceId);
  let claimedAgentId: string | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  const diagnostics = options.diagnostics;
  // A stage on its own never carries a budget or a source: those belong to the
  // timeout branch that actually measured them, so an earlier model slice can
  // never be read against a later stage or a non-timeout failure.
  const atStage = (stage: RegenerationStage) => {
    if (!diagnostics) return;
    diagnostics.stage = stage;
    diagnostics.budgetMs = undefined;
    diagnostics.timeoutSource = undefined;
  };
  const atTimeout = (stage: RegenerationStage, source: TimeoutSource, budgetMs?: number) => {
    if (!diagnostics) return;
    diagnostics.stage = stage;
    diagnostics.budgetMs = budgetMs;
    diagnostics.timeoutSource = source;
  };
  atStage("workspace_read");
  try {
    const workspace = await paseo.workspaces.ref(workspaceId).refresh();
    if (!workspace || workspace.archivingAt) {
      return { status: "skipped", reason: "not_found", workspaceUpdated: false, sessionUpdated: false };
    }
    if (workspace.background || isInsideDirectory(workspace.workspaceDirectory, helperDirectory())) {
      return { status: "skipped", reason: "excluded", workspaceUpdated: false, sessionUpdated: false };
    }

    atStage("agent_list");
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
    // Recorded here, before any early deadline return or throw can lose it.
    if (diagnostics) diagnostics.agentId = agentId;
    atStage("session_select");
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
    if (cancelled()) {
      return { status: "error", reason: "cancelled", workspaceUpdated: false, sessionUpdated: false };
    }
    const remainingBeforeRead = deadlineAt - reserve - now();
    if (remainingBeforeRead <= 0) {
      atTimeout("conversation_read", "task_deadline", remainingBeforeRead);
      return { status: "error", reason: "timeout", workspaceUpdated: false, sessionUpdated: false };
    }
    atStage("conversation_read");
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
      atTimeout("model_generation", "task_deadline", remaining);
      return { status: "error", reason: "timeout", agentId, workspaceUpdated: false, sessionUpdated: false };
    }
    const generationBudget = Math.min(
      options.generationTimeoutMs ?? GENERATION_DEADLINE_MS,
      remaining,
    );
    atStage("model_generation");
    const generation: Promise<ConversationGenerationResult | null> = options.generateConversation({
      transcript,
      ...(conversation.segments && conversation.segments.length > 1 ? { segments: conversation.segments } : {}),
      projectName: workspace.projectDisplayName,
      baseName: workspace.name,
      projectId: workspace.projectId,
      maxChars,
    }, generationBudget, deadlineAt - reserve).catch(() => null);
    // The timer's own measured value, so the line can say how much of the task
    // deadline was actually left when that clock fired.
    const timerMs = Math.max(0, deadlineAt - now());
    const expired = Symbol("expired");
    const timeout = new Promise<typeof expired>((resolve) => {
      timer = setTimeout(() => resolve(expired), timerMs);
    });
    const generated = await Promise.race([generation, timeout]);
    if (!generated || generated === expired) {
      // Only the task timer is a deadline this run measured. A generator that
      // returned no title keeps its previous timeout reason without claiming a
      // clock it never observed.
      if (generated === expired) atTimeout("model_generation", "task_deadline", timerMs);
      else atStage("model_generation");
      return { status: "error", reason: "timeout", agentId, workspaceUpdated: false, sessionUpdated: false };
    }
    if (cancelled()) {
      return { status: "error", reason: "cancelled", agentId, workspaceUpdated: false, sessionUpdated: false };
    }
    const remainingAfterModel = deadlineAt - reserve - now();
    if (remainingAfterModel <= 0) {
      // Not the model slice that ran out, but the whole task deadline: report
      // it as the remaining budget that was actually measured, not the slice.
      // The helper may already have named the clock that stopped it; cleanup
      // crossing the deadline afterwards must not relabel that known failure.
      if (generated.errorCode === "timeout" && generated.timeout) {
        atTimeout("model_generation", generated.timeout.source, generated.timeout.capMs);
      } else {
        atTimeout("model_generation", "task_deadline", remainingAfterModel);
      }
      return { status: "error", reason: "timeout", agentId, workspaceUpdated: false, sessionUpdated: false };
    }
    if (!generated.title) {
      // The helper decides which of its own clocks timed out and whether a turn
      // cap was measured. Without that metadata a helper timeout keeps the
      // previous generic source; any other code (provider, helper terminal,
      // invalid title) is no timeout at all.
      if (generated.errorCode === "timeout") {
        const source = generated.timeout?.source ?? "helper";
        const cap = generated.timeout?.capMs;
        atTimeout("model_generation", source, cap);
      } else {
        atStage("model_generation");
      }
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
    atStage("write_preflight");
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
    if (cancelled()) {
      return { status: "error", reason: "cancelled", agentId, workspaceUpdated: false, sessionUpdated: false };
    }
    const remainingBeforeWrite = deadlineAt - reserve - now();
    if (remainingBeforeWrite <= 0) {
      atTimeout("write_preflight", "task_deadline", remainingBeforeWrite);
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
    // The first write failure is the one the final `reason` reports, and the
    // session block below always runs its own `atStage`. Keep the deciding
    // stage with its budget so the line cannot name a later step.
    let decidingWrite: {
      stage?: RegenerationStage;
      budgetMs?: number;
      timeoutSource?: TimeoutSource;
    } | null = null;

    if (wantsWorkspace) {
      atStage("workspace_write");
      // Same order as before: nothing is sampled once the run is cancelled.
      if (cancelled()) {
        reason = "cancelled";
        skipped = true;
      } else {
        const remainingForWrite = deadlineAt - WRITE_RESERVE_MS - now();
        if (remainingForWrite <= 0) {
          // Its own measured shortfall, so this write timeout is not read as a
          // model timeout that merely ran out of time earlier.
          atTimeout("workspace_write", "task_deadline", remainingForWrite);
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
      // Snapshot once, right here: a timeout keeps its measured shortfall and a
      // write failure keeps no budget, both from the workspace stage.
      if (reason !== undefined && diagnostics) {
        decidingWrite = {
          stage: diagnostics.stage,
          budgetMs: diagnostics.budgetMs,
          timeoutSource: diagnostics.timeoutSource,
        };
      }
    }

    if (wantsSession) {
      atStage("session_write");
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
      } else if (cancelled()) {
        skipped = true;
        reason ??= "cancelled";
      } else {
        // The same single sample as before for the check itself; the rename
        // branch then samples once more for the budget it hands to the CLI.
        const remainingForRename = deadlineAt - 1_000 - now();
        if (remainingForRename <= 0) {
          atTimeout("session_write", "task_deadline", remainingForRename);
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
            // The CLI's own budget can be what failed; keep the existing reason,
            // and record the budget actually handed to it and its source only
            // when this is the failure the line will report.
            if (reason === undefined && renamed.failure === "timeout") {
              atTimeout("session_write", "cli", renameBudget);
            }
            reason ??= "session_write_failed";
            writeFailed = true;
          } else {
            reason ??= "session_verification_failed";
            writeFailed = true;
          }
        }
      }
    }

    // Restore the deciding write's stage on the normal path only: an unexpected
    // throw keeps the stage the run actually reached in the catch below.
    if (decidingWrite && diagnostics) {
      diagnostics.stage = decidingWrite.stage;
      diagnostics.budgetMs = decidingWrite.budgetMs;
      diagnostics.timeoutSource = decidingWrite.timeoutSource;
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

export { MANUAL_GENERATION_DEADLINE_MS };
