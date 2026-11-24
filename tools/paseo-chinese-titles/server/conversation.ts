import type { PaseoApi } from "./paseo-types";
import { buildConversationExcerpt, type ConversationEntry, type ConversationExcerpt } from "../shared/transcript.ts";

/**
 * Bounded two-ended reads. Page counts limit requests and a deadline is
 * checked before each page; neither is a hard timeout for a single refetch,
 * because the timeline RPC accepts no cancellation.
 */
const PAGE_LIMIT = 50;
const MAX_PAGES_PER_SIDE = 8;
const GOAL_VISIBLE = 48;
/** Leave the rest of the RPC budget to the title model and the two writes. */
const SCAN_BUDGET_MS = 5_000;
const MODEL_RESERVE_MS = 4_000;

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

/** Page extents come from every item, so tool-only pages still advance a cursor. */
function seqRange(entries: readonly RawEntry[]): { first?: number; last?: number } {
  let first: number | undefined;
  let last: number | undefined;
  for (const entry of entries) {
    if (typeof entry.seqStart !== "number") continue;
    if (first === undefined || entry.seqStart < first) first = entry.seqStart;
    if (last === undefined || entry.seqStart > last) last = entry.seqStart;
  }
  return { first, last };
}

/**
 * Reads one agent's timeline from both ends, alternating pages so neither side
 * can spend the whole scan before the other starts. It stops on the per-side
 * page cap, the visible-entry goal, a proven timeline edge, a page that came
 * back without a cursor, the point where both scans meet, or a deadline that
 * has passed before the next page. Only `hasOlder`/`hasNewer` false counts as
 * reaching an edge; a missing cursor stops just that side.
 *
 * This is a bounded, evenly sampled excerpt: a very long session can still
 * have an unread stretch between the scans, and the result never claims to be
 * the full transcript.
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

  // Newest first: a tail page, then older pages prepended.
  const tail: ConversationEntry[] = [];
  let tailVisible = 0;
  let tailOldestSeq: number | undefined;
  let tailPages = 0;
  let tailCursor: { epoch: string; seq: number } | undefined;
  /** Only a real `hasOlder: false` proves the scan reached the first item. */
  let tailReachedStart = false;
  /** A missing cursor ends this side without proving anything about the edge. */
  let tailStopped = false;

  // Oldest first: the opening turns, which a tail-only read may never reach.
  const head: ConversationEntry[] = [];
  let headVisible = 0;
  let headNewestSeq: number | undefined;
  let headPages = 0;
  let headCursor: { epoch: string; seq: number } | undefined;
  /** Only a real `hasNewer: false` proves the scan reached the last item. */
  let headReachedEnd = false;
  let headStopped = false;

  let readAttempted = 0;
  let firstPageFailed = false;

  const mayReadTail = () =>
    !tailReachedStart && !tailStopped && tailPages < MAX_PAGES_PER_SIDE && tailVisible < GOAL_VISIBLE;
  const mayReadHead = () =>
    !headReachedEnd && !headStopped && headPages < MAX_PAGES_PER_SIDE && headVisible < GOAL_VISIBLE;

  for (let round = 0; round < MAX_PAGES_PER_SIDE * 2; round += 1) {
    // A scan that proved it reached a timeline edge has seen the whole
    // timeline; a side merely stopped for a missing cursor has not.
    if (tailReachedStart || headReachedEnd) break;
    const canTail = mayReadTail();
    const canHead = mayReadHead();
    if (!canTail && !canHead) break;
    if (headNewestSeq !== undefined && tailOldestSeq !== undefined && headNewestSeq >= tailOldestSeq - 1) break;
    if (outOfTime()) break;
    // Alternate, so both sides get their first page within the first two calls.
    const takeTail = canTail && (!canHead || round % 2 === 0);
    const pageIsFirst = readAttempted === 0;
    try {
      if (takeTail) {
        readAttempted += 1;
        const result = await timeline.refetch({
          direction: tailPages === 0 ? "tail" : "before",
          projection: "projected",
          limit: PAGE_LIMIT,
          ...(tailCursor ? { cursor: tailCursor } : {}),
        });
        // A failed first page means the timeline could not be read at all;
        // a failed later page keeps the bounded content already read.
        if (result.error) {
          if (pageIsFirst) {
            firstPageFailed = true;
            return null;
          }
          break;
        }
        const raw = (result.entries ?? []) as RawEntry[];
        const entries = raw.map(visibleEntry).filter((entry): entry is ConversationEntry => entry !== null);
        // Pages arrive oldest-to-newest, so a newer one belongs after the older ones.
        if (tailPages === 0) tail.push(...entries);
        else tail.unshift(...entries);
        tailVisible += entries.length;
        tailPages += 1;
        const oldest = seqRange(raw).first;
        if (oldest !== undefined) tailOldestSeq = oldest;
        if (!result.hasOlder) {
          tailReachedStart = true;
        } else if (result.startCursor) {
          tailCursor = { epoch: result.startCursor.epoch, seq: result.startCursor.seq };
        } else {
          // No cursor cannot continue this side, but it proves nothing about
          // the start of the timeline; keep whatever the head side read.
          tailStopped = true;
        }
      } else {
        readAttempted += 1;
        const result = await timeline.refetch({
          direction: "after",
          projection: "projected",
          limit: PAGE_LIMIT,
          ...(headCursor ? { cursor: headCursor } : {}),
        });
        // A failed later page keeps what was already read; a failed first page
        // is a read failure, not an empty conversation.
        if (result.error) {
          if (pageIsFirst) firstPageFailed = true;
          break;
        }
        const raw = (result.entries ?? []) as RawEntry[];
        const entries = raw.map(visibleEntry).filter((entry): entry is ConversationEntry => entry !== null);
        head.push(...entries);
        headVisible += entries.length;
        headPages += 1;
        const newest = seqRange(raw).last;
        if (newest !== undefined) headNewestSeq = newest;
        if (!result.hasNewer) {
          headReachedEnd = true;
        } else if (result.endCursor) {
          headCursor = { epoch: result.endCursor.epoch, seq: result.endCursor.seq };
        } else {
          // Same as the tail side: stop this scan, do not claim an edge.
          headStopped = true;
        }
      }
    } catch {
      // A rejected page ends the scan with what is already known; a rejected
      // first page is a read failure, not an empty conversation.
      if (pageIsFirst) firstPageFailed = true;
      break;
    }
  }
  if (firstPageFailed) return null;
  // An edge proof means the whole timeline is already in memory; otherwise
  // combine both bounded samples and let duplicate seq values collapse below.
  const entries = tailReachedStart
    ? tail
    : headReachedEnd
      ? head
      : [...head, ...tail];
  if (entries.length === 0) return buildConversationExcerpt([]);
  // The daemon exposes a stable seq, so sort by it and drop anything the head
  // and tail reads both returned.
  const seen = new Set<string>();
  const unique = entries.filter((entry) => {
    const key = `${entry.seq ?? ""}:${entry.type}:${entry.text ?? ""}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  const timeOf = (value: string | null | undefined) => {
    const parsed = Date.parse(value ?? "");
    return Number.isFinite(parsed) ? parsed : 0;
  };
  unique.sort((left, right) => {
    if (typeof left.seq === "number" && typeof right.seq === "number" && left.seq !== right.seq) {
      return left.seq - right.seq;
    }
    return timeOf(left.timestamp) - timeOf(right.timestamp);
  });
  return buildConversationExcerpt(unique);
}
