/**
 * Rules for repairing a workspace whose automatic title never got past a
 * placeholder.
 *
 * The workspace path names from the first task in one shot. When that model
 * turn fails it writes the deterministic fallback, and records `done` with the
 * failure code, so nothing ever retried it. A workspace could therefore keep a
 * truncated first line while the session that owned its first task already had
 * a verified Chinese title.
 *
 * A repair may adopt such a session title only when the workspace is provably
 * still showing a placeholder the plugin itself left, nobody renamed it, and
 * the donating session is the workspace's first-task owner. A merely non-empty
 * title on some other session is never enough.
 */

import { provisionalTitle, sanitizeConversationTitle } from "./title.ts";

/** Error codes that prove the recorded workspace title is a fallback, not model output. */
const PLACEHOLDER_ERRORS: ReadonlySet<string> = new Set([
  "model_failed",
  "invalid_title",
  "timeout",
  "provider_unavailable",
]);

export interface WorkspaceTitleState {
  status: string;
  /** The title the plugin wrote together with the failure code. */
  title?: string;
  /** The title the workspace had before the plugin wrote the fallback. */
  previousTitle?: string | null;
  error?: string;
  /** True once a verified session title was adopted. */
  repairUsed?: boolean;
  /** True once this workspace spent its one model retry after the fallback. */
  retryUsed?: boolean;
}

export interface SessionTitleState {
  status: string;
  title?: string;
  error?: string;
}

/** True only for a finished workspace entry the plugin left on a fallback title. */
export function isRecordedFallback(state: WorkspaceTitleState | undefined): boolean {
  if (!state || state.status !== "done") return false;
  if (!state.error || !PLACEHOLDER_ERRORS.has(state.error)) return false;
  return Boolean(state.title?.trim());
}

/**
 * True only for a session title this plugin generated and verified: a `done`
 * entry with no failure code whose recorded title is still the live one.
 */
export function isVerifiedSessionTitle(
  state: SessionTitleState | undefined,
  liveTitle: string | null | undefined,
): boolean {
  if (!state || state.status !== "done" || state.error) return false;
  const recorded = state.title?.trim() ?? "";
  return Boolean(recorded) && liveTitle?.trim() === recorded;
}

/**
 * Metadata-only first-task attribution.
 *
 * The repair path must not read another session's message text, so it cannot
 * reuse the timeline-based first-task comparison of the original naming path.
 * It uses list metadata only, and only when that metadata proves one owner:
 *
 * - the fallback title was produced by the workspace's first task, so that task
 *   existed at or before the moment the fallback was recorded; a session
 *   created after that moment cannot have owned it;
 * - a session with no recorded user message never sent a task;
 * - exactly one remaining session is the owner. Two sessions that both predate
 *   the fallback cannot be separated by metadata, so ownership stays unknown
 *   and the workspace is left alone rather than guessed at.
 *
 * A missing or unparsable timestamp also leaves ownership unknown.
 */
export interface OwnershipSession {
  id: string;
  createdAt?: string | null;
  lastUserMessageAt?: string | null;
}

export type FirstTaskOwner =
  | { kind: "owner"; id: string }
  | { kind: "unknown" };

export function pickFirstTaskOwner(
  sessions: readonly OwnershipSession[],
  fallbackRecordedAt: string | null | undefined,
): FirstTaskOwner {
  const fallbackAt = Date.parse(fallbackRecordedAt ?? "");
  if (!Number.isFinite(fallbackAt)) return { kind: "unknown" };
  const candidates: string[] = [];
  for (const session of sessions) {
    if (!session.id || !session.lastUserMessageAt?.trim()) continue;
    const createdAt = Date.parse(session.createdAt ?? "");
    if (!Number.isFinite(createdAt)) return { kind: "unknown" };
    if (createdAt <= fallbackAt) candidates.push(session.id);
  }
  return candidates.length === 1 ? { kind: "owner", id: candidates[0] } : { kind: "unknown" };
}

export type WorkspaceRepairReason =
  | "no_placeholder"
  | "repair_used"
  | "in_flight"
  | "title_changed"
  | "not_first_task"
  | "session_not_verified"
  | "retry_used";

export type WorkspaceRepairDecision =
  | { kind: "repair"; title: string }
  | { kind: "blocked"; reason: WorkspaceRepairReason };

export interface WorkspaceRepairInput {
  workspaceState: WorkspaceTitleState | undefined;
  /** The workspace title read immediately before this decision. */
  liveTitle: string | null | undefined;
  /**
   * The workspace's first real task, but only when the caller already holds it
   * as the owning session's own prompt. `null` means the caller may not read it
   * (the reconcile sweep runs without a session hook); the provisional-text
   * guard is then skipped, which cannot admit a verified title.
   */
  firstTask: string | null;
  /** The live title of that owning session. */
  sessionTitle: string | null | undefined;
  /** That owning session's recorded title state. */
  sessionState: SessionTitleState | undefined;
  /** True only when the session asked about owns the earliest real task. */
  firstTaskOwner: boolean;
  /** False while another naming step holds the workspace. */
  idle: boolean;
  maxChars: number;
}

function isPlaceholderStillShown(input: WorkspaceRepairInput): boolean {
  const state = input.workspaceState;
  const live = input.liveTitle?.trim() ?? "";
  return isRecordedFallback(state) && Boolean(live) && live === state?.title?.trim();
}

/**
 * The other half of the repair: when no verified session title exists yet, one
 * model retry is allowed, and only while the workspace still shows the exact
 * fallback the plugin wrote. A model fallback result is never written again.
 */
export function planWorkspaceRetry(input: {
  workspaceState: WorkspaceTitleState | undefined;
  liveTitle: string | null | undefined;
}): { kind: "retry" } | { kind: "blocked"; reason: WorkspaceRepairReason } {
  const state = input.workspaceState;
  if (!isRecordedFallback(state)) return { kind: "blocked", reason: "no_placeholder" };
  if (state?.repairUsed === true) return { kind: "blocked", reason: "repair_used" };
  if (state?.retryUsed === true) return { kind: "blocked", reason: "retry_used" };
  const live = input.liveTitle?.trim() ?? "";
  if (!live || live !== state?.title?.trim()) return { kind: "blocked", reason: "title_changed" };
  return { kind: "retry" };
}

/**
 * Returns the title to write, or why the workspace stays as it is. The session
 * title must already be a usable Chinese title at the configured length: a
 * repair never truncates or rewrites a verified title.
 */
export function planWorkspaceRepair(input: WorkspaceRepairInput): WorkspaceRepairDecision {
  if (!input.idle) return { kind: "blocked", reason: "in_flight" };
  if (input.workspaceState?.repairUsed === true) return { kind: "blocked", reason: "repair_used" };

  if (!isPlaceholderStillShown(input)) {
    // A recorded fallback that is no longer live was renamed by hand.
    if (isRecordedFallback(input.workspaceState)) return { kind: "blocked", reason: "title_changed" };
    return { kind: "blocked", reason: "no_placeholder" };
  }
  if (!input.firstTaskOwner) return { kind: "blocked", reason: "not_first_task" };
  if (!isVerifiedSessionTitle(input.sessionState, input.sessionTitle)) {
    return { kind: "blocked", reason: "session_not_verified" };
  }

  const candidate = input.sessionTitle?.trim() ?? "";
  // The donating title was produced by this plugin's session gate, so the same
  // gate must leave it untouched: an unchanged value proves it already fits the
  // configured length and reads as Chinese. Anything it would clean, truncate
  // or reject is left for the manual button, because a repair never rewrites a
  // verified title.
  if (!candidate || sanitizeConversationTitle(candidate, input.maxChars) !== candidate) {
    return { kind: "blocked", reason: "session_not_verified" };
  }
  // Writing Paseo's provisional text again would leave the workspace open to
  // the native async summary, so such a value is not a repair.
  if (input.firstTask !== null && candidate === provisionalTitle(input.firstTask)) {
    return { kind: "blocked", reason: "session_not_verified" };
  }
  // A title identical to a title this workspace already had would record a
  // "repair" that changed nothing (or put back the seed placeholder), so the
  // workspace stays on its placeholder until a real title exists.
  const known = [input.workspaceState?.title, input.workspaceState?.previousTitle]
    .map((value) => value?.trim() ?? "")
    .filter(Boolean);
  if (known.includes(candidate)) {
    return { kind: "blocked", reason: "session_not_verified" };
  }
  return { kind: "repair", title: candidate };
}
