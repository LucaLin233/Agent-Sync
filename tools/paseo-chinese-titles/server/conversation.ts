import type { PaseoApi } from "./paseo-types";
import {
  buildTranscriptTurns,
  fitTranscript,
  isSubstantiveAnswer,
  joinTurns,
  planSegments,
  type ConversationEntry,
  type ConversationExcerpt,
  type TranscriptCoverage,
} from "../shared/transcript.ts";

/**
 * Chronological page budget. The scan walks forward from the head so every
 * readable turn is covered in order; it never samples. Page count, visible
 * entries, characters and a page-level deadline all bound the work.
 */
const PAGE_LIMIT = 100;
const MAX_PAGES = 40;
const MAX_VISIBLE_ENTRIES = 3_000;
const MAX_TRANSCRIPT_CHARS = 30_000;
/** Leave the rest of the RPC budget to the model runs and the two writes. */
const SCAN_BUDGET_MS = 5_000;
const MODEL_RESERVE_MS = 4_000;
/**
 * Model input per contiguous segment and how many segments one title may use.
 * Two 15k-character parts usually hold the whole 30k read budget, so an
 * ordinary session is not cut again after being read. A turn-dense read whose
 * labels push it past the segment budget is reported as `segment_cap` partial,
 * never presented as a complete summary.
 */
const SEGMENT_CHARS = 15_000;
const MAX_SEGMENTS = 2;
/**
 * Per-message clip for the manual summary. Long answers matter, but a session
 * is covered by how many turns fit, not by one giant message: this keeps a
 * 30 000-character read to roughly a dozen substantive turns.
 */
const MESSAGE_CHARS = 1_000;

/** A session title needs only the opening question and the answer that followed. */
const NAMING_PAGE_LIMIT = 100;
const NAMING_MAX_PAGES = 10;
const NAMING_MAX_ENTRIES = 400;

export interface ReadConversationOptions {
  /** Absolute epoch milliseconds for the whole RPC; caps the scan window. */
  deadlineAt?: number;
}

interface RawEntry {
  item: { type: string };
  turnId?: string | null;
  timestamp?: string;
  seqStart?: number;
}

/**
 * Paseo 0.17.4's timeline store answers a stale cursor or a sequence gap by
 * resetting the page to the tail. Such a page can end with `hasNewer: false`
 * even though earlier items were skipped, so a discontinuity is never treated
 * as a completed forward scan.
 */
export function isDiscontinuous(page: {
  reset?: boolean;
  staleCursor?: boolean;
  gap?: boolean;
}): boolean {
  return page.reset === true || page.staleCursor === true || page.gap === true;
}

function itemText(item: unknown): string | null {
  if (!item || typeof item !== "object") return null;
  const text = (item as { text?: unknown }).text;
  return typeof text === "string" ? text : null;
}

/** Visible conversation prose only; every other item type stays out of scope. */
function visibleEntry(entry: RawEntry): ConversationEntry | null {
  if (entry.item.type !== "user_message" && entry.item.type !== "assistant_message") return null;
  const text = itemText(entry.item);
  if (!text || !text.trim()) return null;
  return {
    type: entry.item.type,
    text,
    turnId: entry.turnId ?? null,
    timestamp: entry.timestamp,
    seq: entry.seqStart,
  };
}

/**
 * Reads one agent's timeline from the start in chronological order until the
 * end, a page/entry/character cap or the scan deadline. The excerpt carries
 * `coverage`: `full` only when the read proved it reached the newest item and
 * every readable turn fits the segment budget. A long or partially readable
 * session is reported as `partial` with a reason instead of being sampled and
 * presented as complete.
 *
 * This is a page-level deadline, not a hard cancellation: the timeline refetch
 * accepts no signal, so a page already sent may finish after the deadline.
 */
export async function readSessionConversation(
  paseo: PaseoApi,
  agentId: string,
  options: ReadConversationOptions = {},
): Promise<ConversationExcerpt | null> {
  const timeline = paseo.agents.ref(agentId).timeline;
  const startedAt = Date.now();
  const windowEnd = options.deadlineAt === undefined
    ? startedAt + SCAN_BUDGET_MS
    : Math.min(startedAt + SCAN_BUDGET_MS, options.deadlineAt - MODEL_RESERVE_MS);
  const outOfTime = () => Date.now() >= windowEnd;

  const entries: ConversationEntry[] = [];
  let cursor: { epoch: string; seq: number } | undefined;
  let pages = 0;
  let chars = 0;
  let reachedEnd = false;
  let coverage: TranscriptCoverage = { kind: "full" };
  const partial = (reason: TranscriptCoverage["reason"]) => {
    coverage = { kind: "partial", reason };
  };

  for (;;) {
    if (pages >= MAX_PAGES) {
      partial("page_cap");
      break;
    }
    if (entries.length >= MAX_VISIBLE_ENTRIES) {
      partial("entry_cap");
      break;
    }
    if (outOfTime()) {
      partial("deadline");
      break;
    }
    const pageIsFirst = pages === 0;
    let result: Awaited<ReturnType<typeof timeline.refetch>>;
    try {
      result = await timeline.refetch({
        direction: "after",
        projection: "projected",
        limit: PAGE_LIMIT,
        ...(cursor ? { cursor } : {}),
      });
    } catch {
      // A failed first page is a read failure, not an empty conversation.
      if (pageIsFirst) return null;
      partial("read_error");
      break;
    }
    if (result.error) {
      if (pageIsFirst) return null;
      partial("read_error");
      break;
    }
    // The daemon reset or skipped ahead and served a tail page. Its
    // `hasNewer: false` says nothing about earlier items, and the page is not
    // contiguous with what was read before, so pages read so far stay the
    // content and the read is reported as partial. Only a first-page reset,
    // where nothing earlier is readable at all, uses that tail page itself.
    const discontinuous = isDiscontinuous(result);
    if (!discontinuous || pageIsFirst) {
      for (const entry of (result.entries ?? []) as RawEntry[]) {
        const visible = visibleEntry(entry);
        if (!visible) continue;
        entries.push(visible);
        chars += visible.text?.length ?? 0;
        if (entries.length >= MAX_VISIBLE_ENTRIES || chars >= MAX_TRANSCRIPT_CHARS) break;
      }
    }
    pages += 1;
    if (discontinuous) {
      partial(result.gap === true ? "gap" : "reset");
      break;
    }
    if (entries.length >= MAX_VISIBLE_ENTRIES) {
      partial("entry_cap");
      break;
    }
    if (chars >= MAX_TRANSCRIPT_CHARS) {
      partial("char_cap");
      break;
    }
    if (!result.hasNewer) {
      reachedEnd = true;
      break;
    }
    if (!result.endCursor) {
      // No cursor cannot continue, and it proves nothing about the tail.
      partial("cursor_missing");
      break;
    }
    cursor = { epoch: result.endCursor.epoch, seq: result.endCursor.seq };
  }

  if (!reachedEnd && coverage.kind === "full") partial("cursor_missing");
  // The daemon exposes a stable seq; drop duplicates in case a page overlaps.
  const seen = new Set<string>();
  const unique = entries.filter((entry) => {
    const key = `${entry.seq ?? ""}:${entry.type}:${entry.text ?? ""}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  unique.sort((left, right) => {
    if (typeof left.seq === "number" && typeof right.seq === "number" && left.seq !== right.seq) {
      return left.seq - right.seq;
    }
    const timeOf = (value: string | null | undefined) => {
      const parsed = Date.parse(value ?? "");
      return Number.isFinite(parsed) ? parsed : 0;
    };
    return timeOf(left.timestamp) - timeOf(right.timestamp);
  });

  const turns = buildTranscriptTurns(unique, { maxMessageChars: MESSAGE_CHARS });
  if (turns.length === 0) {
    // Nothing readable and the read was cut short: that is a read failure, not
    // an empty conversation. A clean read of an empty timeline stays empty.
    if (coverage.kind === "partial") return null;
    return { text: "", turns: 0, segments: [], coveredTurns: 0, coverage };
  }
  const plan = planSegments(turns, { segmentChars: SEGMENT_CHARS, maxSegments: MAX_SEGMENTS });
  const segments = plan.segments.map((segment) => joinTurns(segment));
  // A read that reached the end but not the segment budget still lost turns;
  // never report that as full coverage.
  if (coverage.kind === "full" && !plan.coversAll) partial("segment_cap");
  return {
    text: segments.join("\n\n"),
    turns: turns.length,
    segments,
    coveredTurns: plan.coveredTurns,
    coverage,
  };
}

export interface NamingMaterial {
  /** The session's first visible user question, redacted and clipped. */
  question: string;
  /** The substantive assistant answer of the completed turn, or null. */
  answer: string | null;
  /** The turn whose answer this material carries. */
  turnId: string | null;
}

/**
 * Reads just enough of the opening to name a session: the first user question
 * and the assistant answer to the turn that triggered naming. A turn with no
 * substantive answer (tool-only, failed, canceled) yields `answer: null`, so
 * the caller keeps its provisional title and spends no naming attempt.
 *
 * The scan walks forward from the opening and stops once the named turn has an
 * answer and the next user message is reached, or at the page/deadline cap.
 */
export async function readSessionNamingMaterial(
  paseo: PaseoApi,
  agentId: string,
  options: { turnId?: string | null; deadlineAt?: number } = {},
): Promise<NamingMaterial | null> {
  const timeline = paseo.agents.ref(agentId).timeline;
  const startedAt = Date.now();
  const windowEnd = options.deadlineAt === undefined
    ? startedAt + SCAN_BUDGET_MS
    : Math.min(startedAt + SCAN_BUDGET_MS, options.deadlineAt - MODEL_RESERVE_MS);
  const targetTurn = options.turnId ?? null;

  const entries: ConversationEntry[] = [];
  let cursor: { epoch: string; seq: number } | undefined;
  let openingTurn: string | null | undefined;
  let answered = false;

  for (let page = 0; page < NAMING_MAX_PAGES; page += 1) {
    let result: Awaited<ReturnType<typeof timeline.refetch>>;
    try {
      result = await timeline.refetch({
        direction: "after",
        projection: "projected",
        limit: NAMING_PAGE_LIMIT,
        ...(cursor ? { cursor } : {}),
      });
    } catch {
      if (page === 0) return null;
      break;
    }
    if (result.error) {
      if (page === 0) return null;
      break;
    }
    // A reset or gap page jumps to the tail; its first user message is not the
    // session's opening, so it cannot be used as naming material.
    if (isDiscontinuous(result)) return null;

    let stop = false;
    // All assistant prose of the target turn is naming material; a preamble
    // before a tool call must not hide the turn's real final answer.
    for (const raw of (result.entries ?? []) as RawEntry[]) {
      const visible = visibleEntry(raw);
      if (!visible) continue;
      if (visible.type === "user_message" && openingTurn === undefined) {
        openingTurn = visible.turnId ?? null;
      }
      const target = targetTurn ?? openingTurn ?? null;
      // Once the target answer is in hand, the first visible row belonging to
      // any other turn closes the material; nothing later can belong to it.
      if (answered && target !== null && (visible.turnId ?? null) !== target) {
        stop = true;
        break;
      }
      entries.push(visible);
      if (visible.type === "assistant_message") {
        const turn = visible.turnId ?? null;
        const ofTarget = targetTurn === null ? turn === (openingTurn ?? null) : turn === targetTurn;
        if (ofTarget && isSubstantiveAnswer(visible.text)) answered = true;
      }
      if (entries.length >= NAMING_MAX_ENTRIES) {
        stop = true;
        break;
      }
    }
    if (stop || !result.hasNewer || !result.endCursor) break;
    cursor = { epoch: result.endCursor.epoch, seq: result.endCursor.seq };
    if (Date.now() >= windowEnd) break;
  }

  // A tool-dense opening can exhaust the forward page budget before the
  // answer. The completed turn is usually the newest one, so one bounded tail
  // read recovers just that turn; if a newer turn already started the page
  // holds nothing for this turn and the material stays answer-less.
  if (!answered && targetTurn !== null && Date.now() < windowEnd) {
    try {
      const tail = await timeline.refetch({ direction: "tail", projection: "projected", limit: 1, wholeTurns: true });
      if (!tail.error) {
        for (const raw of (tail.entries ?? []) as RawEntry[]) {
          const visible = visibleEntry(raw);
          if (!visible || visible.type !== "assistant_message") continue;
          if ((visible.turnId ?? null) === targetTurn && isSubstantiveAnswer(visible.text)) {
            entries.push(visible);
            answered = true;
            break;
          }
        }
      }
    } catch {
      // Keep whatever the forward scan found; no attempt is spent without an answer.
    }
  }

  const firstUser = entries.find((entry) => entry.type === "user_message");
  if (!firstUser || !firstUser.text?.trim()) return null;
  const questionTurns = buildTranscriptTurns([firstUser], { maxMessageChars: 1_200 });
  const question = questionTurns[0]?.text.replace(/^用户：/u, "") ?? "";
  if (!question.trim()) return null;

  const turn = targetTurn ?? openingTurn ?? null;
  if (turn === null) return { question, answer: null, turnId: null };
  const answers = entries.filter((entry) =>
    entry.type === "assistant_message" && (entry.turnId ?? null) === turn && isSubstantiveAnswer(entry.text));
  const answerTurns = buildTranscriptTurns(answers, { maxMessageChars: 1_800 })
    .map((entry) => ({ id: entry.id, text: entry.text.replace(/^助手：/u, ""), chars: entry.chars }));
  // All answer parts of the completed turn, in order: a short preamble must not
  // be the only thing the naming model sees.
  const answer = fitTranscript(answerTurns, 1_800).trim();
  return { question, answer: answer ? answer : null, turnId: turn };
}
