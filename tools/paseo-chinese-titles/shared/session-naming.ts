/**
 * Pure rules for automatic session naming.
 *
 * A session is named only after its first turn produced a substantive answer,
 * from the first question and that answer together. One failed model attempt
 * keeps the provisional title and allows exactly one more attempt on a later,
 * different completed turn; after that the session is left alone. Duplicate
 * events for the same turn, a restart and concurrent hooks all spend at most
 * the already-recorded attempt.
 */

export type SessionNamingBlockedReason =
  | "manual_title"
  | "legacy"
  | "exhausted"
  | "in_flight";

export type SessionNamingWaitReason =
  | "awaiting_answer"
  | "duplicate_turn"
  | "no_new_turn";

export type SessionNamingAction =
  | { kind: "wait"; reason: SessionNamingWaitReason }
  | { kind: "blocked"; reason: SessionNamingBlockedReason }
  | { kind: "generate"; attempt: number; repair: boolean };

export interface SessionNamingState {
  status: "legacy" | "pending" | "generating" | "done" | "skipped" | "error";
  title?: string;
  error?: string;
  at: string;
  attempts?: number;
  lastTurnId?: string | null;
  repairUsed?: boolean;
}

export interface SessionNamingInput {
  state: SessionNamingState | undefined;
  /** The live session title right now. */
  currentTitle: string | null | undefined;
  /** The first visible user prompt; used to recognise Paseo's provisional title. */
  prompt: string;
  /** True only when this hook observed a completed turn with a substantive answer. */
  hasAnswer: boolean;
  /** The turn this hook belongs to; null on a reconcile scan without a turn. */
  turnId: string | null;
  /** False on `agent.turn.before` and on a reconcile scan. */
  completed: boolean;
  maxAttempts: number;
  /** True when the current title is still Paseo's provisional first-prompt text. */
  provisional: boolean;
}

/**
 * A historical `done` entry that carries `model_failed` may be the old code's
 * first-sentence truncation, not a model title. It is repairable once, but only
 * while the live title is exactly the title that entry recorded, i.e. nobody
 * renamed the session by hand since.
 */
/**
 * A `done` entry the old code wrote while its model failed: the live title may
 * still be that deterministic fallback. Such an entry is inspected on later
 * completed turns until one of them proves (by a different live title) that the
 * user renamed it, or the single repair is spent.
 */
export function isUnrepairedLegacyEntry(state: SessionNamingState | undefined): boolean {
  if (!state || state.status !== "done") return false;
  if (state.error !== "model_failed" && state.error !== "provider_unavailable") return false;
  return state.repairUsed !== true && Boolean(state.title?.trim());
}

export function isLegacyRepairCandidate(
  state: SessionNamingState | undefined,
  currentTitle: string | null | undefined,
): boolean {
  if (!state || state.status !== "done") return false;
  // The old automatic path wrote a deterministic fallback title and still
  // recorded `done`. Both error codes prove the live title is not a model
  // title; anything else (or no code) is treated as a real title.
  if (state.error !== "model_failed" && state.error !== "provider_unavailable") return false;
  if (state.repairUsed === true) return false;
  if (!state.title?.trim()) return false;
  return currentTitle?.trim() === state.title.trim();
}

function isRepairCandidate(input: SessionNamingInput): boolean {
  return isLegacyRepairCandidate(input.state, input.currentTitle);
}

export function planSessionNaming(input: SessionNamingInput): SessionNamingAction {
  const { state, maxAttempts } = input;
  if (state?.status === "legacy") return { kind: "blocked", reason: "legacy" };

  if (isRepairCandidate(input)) {
    // The repair is the same one chance as any other attempt: it needs a real
    // answer from a turn that actually completed. A failed or canceled turn may
    // still have partially streamed assistant text, and that must not spend the
    // single repair.
    if (!input.completed || !input.hasAnswer) return { kind: "wait", reason: "awaiting_answer" };
    return { kind: "generate", attempt: (state?.attempts ?? 1) + 1, repair: true };
  }

  // Any title that is neither Paseo's provisional text nor our own unverified
  // one is an explicit or manual title and stays untouched.
  if (!input.provisional) return { kind: "blocked", reason: "manual_title" };

  if (state?.status === "done" || state?.status === "skipped") {
    return { kind: "blocked", reason: state.status === "skipped" ? "exhausted" : "manual_title" };
  }
  if (state?.status === "generating") return { kind: "blocked", reason: "in_flight" };

  const attempts = state?.attempts ?? 0;
  if (attempts >= maxAttempts) return { kind: "blocked", reason: "exhausted" };

  // A non-completed hook, a failed or canceled turn, or a turn that only ran
  // tools never spends an attempt.
  if (!input.completed || !input.hasAnswer) return { kind: "wait", reason: "awaiting_answer" };

  // A reconcile scan carries no turn id. It may only make the first attempt;
  // after that a retry must come from a provably different completed turn.
  if (input.turnId === null) {
    if (attempts > 0) return { kind: "wait", reason: "no_new_turn" };
    return { kind: "generate", attempt: 1, repair: false };
  }

  // The same turn redelivered (duplicate event, restart, retry of the hook)
  // must not spend a second attempt.
  if (state?.lastTurnId && state.lastTurnId === input.turnId) {
    return { kind: "wait", reason: "duplicate_turn" };
  }
  return { kind: "generate", attempt: attempts + 1, repair: false };
}

/**
 * Records a verified model title. A repair ends even if it produced this title.
 */
export function afterSessionSuccess(input: {
  title: string;
  attempt: number;
  turnId: string | null;
  repair: boolean;
  at: string;
}): SessionNamingState {
  return {
    status: "done",
    at: input.at,
    title: input.title,
    attempts: input.attempt,
    lastTurnId: input.turnId,
    ...(input.repair ? { repairUsed: true } : {}),
  };
}

/**
 * Records a spent attempt that produced no usable title. The live provisional
 * title is never replaced by a fallback: the entry stays `pending` for one
 * later completed turn, or `skipped` once both attempts are spent. A
 * provider-unavailable failure keeps that one later chance too, because the
 * provider may have recovered by then; a repairable legacy entry stops after
 * its single repair attempt.
 *
 * `status` is never `done`, and no `title` is stored, so the old first-sentence
 * truncation cannot be reported as success.
 */
export function afterSessionFailure(input: {
  errorCode: string;
  attempt: number;
  maxAttempts: number;
  turnId: string | null;
  repair: boolean;
  at: string;
}): SessionNamingState {
  const exhausted = input.attempt >= input.maxAttempts;
  const stopNow = exhausted || input.repair;
  return {
    status: stopNow ? "skipped" : "pending",
    at: input.at,
    error: input.errorCode,
    attempts: input.attempt,
    lastTurnId: input.turnId,
    ...(input.repair ? { repairUsed: true } : {}),
  };
}
