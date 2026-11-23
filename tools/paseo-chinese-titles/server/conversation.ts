import type { PaseoApi } from "./paseo-types";
import { buildConversationExcerpt, type ConversationEntry, type ConversationExcerpt } from "../shared/transcript.ts";

/** Bounded reads: three tail pages plus one bounded scan for the first task. */
const TAIL_PAGE_LIMIT = 40;
const TAIL_MAX_PAGES = 3;
const HEAD_PAGE_LIMIT = 20;
const HEAD_MAX_PAGES = 10;

function itemText(item: unknown): string | null {
  if (!item || typeof item !== "object") return null;
  const text = (item as { text?: unknown }).text;
  return typeof text === "string" ? text : null;
}

/**
 * Reads one agent's timeline tail and its earliest user message. Only item
 * types and visible text are kept; tool calls, reasoning, notifications,
 * todos, compaction and plugin rows never leave this function's output.
 */
export async function readSessionConversation(
  paseo: PaseoApi,
  agentId: string,
): Promise<ConversationExcerpt | null> {
  const timeline = paseo.agents.ref(agentId).timeline;
  const pages: ConversationEntry[][] = [];
  let cursor: { epoch: string; seq: number } | undefined;
  // The tail always has user messages in a long session; only `hasOlder`
  // tells us whether the read actually reached the beginning of the timeline.
  let reachedStart = false;

  for (let page = 0; page < TAIL_MAX_PAGES; page += 1) {
    const result = page === 0
      ? await timeline.refetch({ direction: "tail", projection: "projected", limit: TAIL_PAGE_LIMIT })
      : await timeline.refetch({ direction: "before", projection: "projected", limit: TAIL_PAGE_LIMIT, cursor });
    if (result.error) return null;
    const entries = (result.entries ?? []).map((entry) => ({
      type: entry.item.type,
      text: itemText(entry.item),
      turnId: entry.turnId ?? null,
      timestamp: entry.timestamp,
      seq: entry.seqStart,
    }));
    // Pages arrive oldest-to-newest; an older page belongs before the newer ones.
    if (page === 0) pages.push(entries);
    else pages.unshift(entries);
    if (!result.hasOlder) {
      reachedStart = true;
      break;
    }
    if (!result.startCursor) break;
    cursor = result.startCursor;
  }

  const entries = pages.flat();
  if (!reachedStart) {
    // The tail did not reach the beginning: add the earliest real user message
    // so the summary still explains why the session started. Bounded like the
    // tail read, and only a user_message counts.
    let headCursor: { epoch: string; seq: number } | undefined;
    for (let page = 0; page < HEAD_MAX_PAGES; page += 1) {
      const result = await timeline.refetch({
        direction: "after",
        projection: "projected",
        limit: HEAD_PAGE_LIMIT,
        ...(headCursor ? { cursor: headCursor } : {}),
      });
      if (result.error) break;
      const first = (result.entries ?? []).find(
        (entry) => entry.item.type === "user_message" && (itemText(entry.item) ?? "").trim(),
      );
      if (first) {
        entries.unshift({
          type: first.item.type,
          text: itemText(first.item),
          turnId: first.turnId ?? null,
          timestamp: first.timestamp,
          seq: first.seqStart,
        });
        break;
      }
      if (!result.hasNewer || !result.endCursor) break;
      headCursor = result.endCursor;
    }
  }

  // Page order is not needed for correctness: the daemon exposes a stable seq,
  // so sort by it and drop anything the tail and head reads both returned.
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
