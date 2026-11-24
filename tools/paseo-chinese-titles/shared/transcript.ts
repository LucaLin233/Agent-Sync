/**
 * Turns visible timeline entries into chronological, redacted text blocks.
 *
 * Only visible user text and assistant answers are considered: reasoning, tool
 * calls, notifications, todo/compaction records and plugin rows are dropped by
 * the caller. Obvious credentials are redacted here so they never reach the
 * helper session, an RPC reply, a log or a file.
 *
 * The manual summary reads the transcript in chronological page order and
 * covers every readable turn. A single long turn can still be clipped, and a
 * session longer than the bounded budget is reported as partial coverage rather
 * than silently sampled; see `planSegments` and `server/conversation.ts`.
 */

export interface ConversationEntry {
  type: string;
  text?: string | null;
  turnId?: string | null;
  timestamp?: string | null;
  seq?: number;
}

export interface ExcerptOptions {
  /** Maximum characters of the final excerpt. */
  maxChars?: number;
  /** Maximum characters of one message. */
  maxMessageChars?: number;
}

export interface ConversationExcerpt {
  /** Joined segments, in chronological order. */
  text: string;
  turns: number;
  /** Contiguous chronological groups, each within the model input budget. */
  segments: string[];
  /** Turns that made it into `segments`; equal to `turns` for full coverage. */
  coveredTurns: number;
  coverage: TranscriptCoverage;
}

/** One conversation turn, already grouped, filtered, redacted and clipped. */
export interface TranscriptTurn {
  id: string | null;
  text: string;
  chars: number;
}

export type TranscriptPartialReason =
  | "page_cap"
  | "entry_cap"
  | "char_cap"
  | "deadline"
  | "cursor_missing"
  | "read_error"
  | "segment_cap"
  | "reset"
  | "gap";

export interface TranscriptCoverage {
  kind: "full" | "partial";
  /** Why only part of the timeline could be read; absent for a full read. */
  reason?: TranscriptPartialReason;
}

const REDACTIONS: ReadonlyArray<readonly [RegExp, string]> = [
  [/-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----/gu, "[已移除私钥]"],
  [/\bgithub_pat_[A-Za-z0-9_]{10,}/gu, "[已移除凭据]"],
  [/\bgh[pousr]_[A-Za-z0-9]{10,}/gu, "[已移除凭据]"],
  [/\bxox[abposr]-[A-Za-z0-9-]{10,}/gu, "[已移除凭据]"],
  [/\bAKIA[0-9A-Z]{16}\b/gu, "[已移除凭据]"],
  [/\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}/gu, "[已移除令牌]"],
  [/\b(?:sk|pk|rk)-[A-Za-z0-9_-]{16,}/gu, "[已移除凭据]"],
  [/\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{8,}/giu, "$1 [已移除凭据]"],
  [
    /\b[A-Z][A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|ACCESS_KEY|PRIVATE_KEY)[A-Z0-9_]*\s*=\s*\S+/gu,
    "[已移除凭据赋值]",
  ],
  [
    /["']?(?:api[-_ ]?key|apikey|access[-_ ]?token|refresh[-_ ]?token|auth[-_ ]?token|client[-_ ]?secret|secret|password|passwd|pwd|authorization)["']?\s*[:=]\s*(?:"[^"]*"|'[^']*'|[^\s,;}]+)/giu,
    "[已移除凭据]",
  ],
];

/** Removes credentials a summary has no business carrying anywhere. */
export function redactSecrets(text: string): string {
  let value = text;
  for (const [pattern, replacement] of REDACTIONS) value = value.replace(pattern, replacement);
  return value;
}

/** Harness blocks a user message may carry: instructions, permissions, skills, system rows. */
const HARNESS_BLOCKS: ReadonlyArray<RegExp> = [
  /<environment_context>[\s\S]*?<\/environment_context>/giu,
  /<paseo-system\b[\s\S]*?<\/paseo-system>/giu,
  /<user_instructions>[\s\S]*?<\/user_instructions>/giu,
  /<permissions instructions>[\s\S]*?<\/permissions instructions>/giu,
  /<skills_instructions>[\s\S]*?<\/skills_instructions>/giu,
  /<collaboration_mode>[\s\S]*?<\/collaboration_mode>/giu,
  /<INSTRUCTIONS>[\s\S]*?<\/INSTRUCTIONS>/giu,
  /^# AGENTS\.md instructions[^\n]*\n/imu,
  /<attachment[\s\S]*?<\/attachment>/giu,
];

/** Large fenced output is not conversation; keep a marker so the model still sees a topic shift. */
function withoutBulk(text: string): string {
  return text.replace(/```[\s\S]{300,}?```/gu, "[此处省略一段代码或命令输出]");
}

/**
 * A user message may also carry tool-injected blocks. Drop those and lone
 * attachment lines, then keep the remaining visible prose.
 */
export function withoutInjectedBlocks(text: string): string {
  let value = text;
  for (const pattern of HARNESS_BLOCKS) value = value.replace(pattern, " ");
  value = withoutBulk(value)
    .split(/\r?\n/u)
    .filter((line) => !/^\s*\[(?:附件|attachment)[^\]]*\]\s*$/iu.test(line) &&
      !/^\s*(?:附件|attachment)\s*[:：]/iu.test(line))
    .join("\n");
  return value;
}

function normalize(text: string): string {
  return text
    .replace(/\r\n?/gu, "\n")
    .replace(/[ \t]+/gu, " ")
    .replace(/\n{3,}/gu, "\n\n")
    .trim();
}

const TOKEN_CHAR = /[A-Za-z0-9_.\-/@#]/u;

function clip(text: string, maxChars: number): string {
  const chars = Array.from(text);
  if (chars.length <= maxChars) return text;
  // The ellipsis is part of the budget.
  let end = Math.max(1, maxChars - 1);
  // Never cut an ASCII token in half: back off to the previous boundary.
  if (TOKEN_CHAR.test(chars[end] ?? "") && TOKEN_CHAR.test(chars[end - 1] ?? "")) {
    while (end > 0 && TOKEN_CHAR.test(chars[end - 1] ?? "")) end -= 1;
  }
  const cut = chars.slice(0, Math.max(1, end)).join("").replace(/[\s,;:，。；：、\-/·]+$/u, "");
  return cut ? `${cut}…` : "";
}

function lengthOf(value: string): number {
  return Array.from(value).length;
}

const ROLE_LABEL: Readonly<Record<string, string>> = {
  user_message: "用户",
  assistant_message: "助手",
};

/** A completed turn needs at least this much visible prose to count as an answer. */
export const MIN_ANSWER_CHARS = 4;

/**
 * True when the visible assistant text can carry a real answer. A turn that
 * only ran tools, or a failed/canceled turn, must not spend the one naming
 * retry; the caller waits for the next completed turn instead.
 */
export function isSubstantiveAnswer(text: string | null | undefined): boolean {
  if (typeof text !== "string" || !text.trim()) return false;
  const cleaned = redactSecrets(normalize(withoutInjectedBlocks(text))).replace(/\s+/gu, "");
  return Array.from(cleaned).length >= MIN_ANSWER_CHARS;
}

/**
 * Groups chronological entries by turn id, keeps the user's question before
 * the answer of its own turn, and clips each message to a fixed size. Entries
 * without a turn id become their own turn.
 */
export function buildTranscriptTurns(
  entries: readonly ConversationEntry[],
  options: ExcerptOptions = {},
): TranscriptTurn[] {
  const maxMessageChars = options.maxMessageChars ?? 1_600;
  const turns: Array<{ id: string | null; parts: string[] }> = [];
  const indexByKey = new Map<string, number>();
  let lastText = "";
  for (const entry of entries) {
    const label = ROLE_LABEL[entry.type];
    if (!label || typeof entry.text !== "string") continue;
    const cleaned = redactSecrets(normalize(withoutInjectedBlocks(entry.text)));
    if (!cleaned || cleaned === lastText) continue;
    // The transcript carries the user's visible questions and the assistant's
    // substantive answers, not one-word acknowledgements or tool chatter.
    if (entry.type === "assistant_message" && !isSubstantiveAnswer(cleaned)) continue;
    lastText = cleaned;
    const key = entry.turnId ? `turn:${entry.turnId}` : `solo:${turns.length}`;
    let index = indexByKey.get(key);
    if (index === undefined) {
      index = turns.length;
      indexByKey.set(key, index);
      turns.push({ id: entry.turnId ?? null, parts: [] });
    }
    turns[index].parts.push(`${label}：${clip(cleaned, maxMessageChars)}`);
  }
  return turns
    .map((turn) => {
      const text = normalize(turn.parts.join("\n"));
      return { id: turn.id, text, chars: lengthOf(text) };
    })
    .filter((turn) => turn.text.length > 0);
}

export function joinTurns(turns: readonly TranscriptTurn[]): string {
  return turns.map((turn) => turn.text).join("\n\n");
}

/**
 * Splits the character budget evenly across turns, then lets the leftovers of
 * short turns flow to longer ones, so one long answer cannot starve the rest.
 */
function allocate(sizes: readonly number[], budget: number): number[] {
  const allocation = new Array(sizes.length).fill(0) as number[];
  if (sizes.length === 0) return allocation;
  const share = Math.floor(budget / sizes.length);
  let remaining = budget;
  for (let index = 0; index < sizes.length; index += 1) {
    const give = Math.min(sizes[index], share, remaining);
    allocation[index] = give;
    remaining -= give;
  }
  for (let round = 0; round < sizes.length && remaining > 0; round += 1) {
    const open = allocation.map((value, index) => (value < sizes[index] ? index : -1)).filter((index) => index >= 0);
    if (open.length === 0) break;
    const each = Math.max(1, Math.floor(remaining / open.length));
    for (const index of open) {
      const give = Math.min(each, sizes[index] - allocation[index], remaining);
      allocation[index] += give;
      remaining -= give;
      if (remaining <= 0) break;
    }
  }
  return allocation;
}

/**
 * Joins turns verbatim while they fit, then shares the remaining budget evenly
 * across them. Used for a short session and for the first-question/answer pair
 * of an automatically named session.
 */
export function fitTranscript(turns: readonly TranscriptTurn[], maxChars: number): string {
  if (turns.length === 0) return "";
  const joined = joinTurns(turns);
  if (lengthOf(joined) <= maxChars) return joined;
  const separators = 2 * Math.max(0, turns.length - 1);
  const allocation = allocate(turns.map((turn) => turn.chars), Math.max(0, maxChars - separators));
  const text = normalize(
    turns
      .map((turn, index) => (allocation[index] > 0 ? clip(turn.text, allocation[index]) : ""))
      .filter(Boolean)
      .join("\n\n"),
  );
  return lengthOf(text) <= maxChars ? text : Array.from(text).slice(0, maxChars).join("").trim();
}

/** Bounded excerpt over a list of entries; a short conversation passes through verbatim. */
export function buildConversationExcerpt(
  entries: readonly ConversationEntry[],
  options: ExcerptOptions = {},
): ConversationExcerpt {
  const maxChars = options.maxChars ?? 2_400;
  const turns = buildTranscriptTurns(entries, {
    maxMessageChars: Math.min(options.maxMessageChars ?? 1_200, maxChars),
  });
  if (turns.length === 0) {
    return { text: "", turns: 0, segments: [], coveredTurns: 0, coverage: { kind: "full" } };
  }
  return {
    text: fitTranscript(turns, maxChars),
    turns: turns.length,
    segments: [joinTurns(turns)],
    coveredTurns: turns.length,
    coverage: { kind: "full" },
  };
}

export interface SegmentPlan {
  /** Contiguous chronological groups, in order. */
  segments: TranscriptTurn[][];
  coveredTurns: number;
  /** True only when every readable turn is inside some segment. */
  coversAll: boolean;
}

/**
 * Cuts the transcript into contiguous chronological segments that each fit the
 * model input, up to `maxSegments`. When the session is longer, the plan stops
 * early and `coversAll` is false: the caller must report partial coverage
 * instead of claiming a whole-session summary.
 */
export function planSegments(
  turns: readonly TranscriptTurn[],
  options: { segmentChars?: number; maxSegments?: number } = {},
): SegmentPlan {
  const segmentChars = Math.max(500, options.segmentChars ?? 6_000);
  const maxSegments = Math.max(1, options.maxSegments ?? 3);
  const segments: TranscriptTurn[][] = [];
  let current: TranscriptTurn[] = [];
  let size = 0;
  for (const turn of turns) {
    if (segments.length >= maxSegments) break;
    const extra = turn.chars + (current.length > 0 ? 2 : 0);
    if (current.length > 0 && size + extra > segmentChars) {
      segments.push(current);
      current = [];
      size = 0;
      if (segments.length >= maxSegments) break;
    }
    current.push(turn);
    size += turn.chars + (current.length > 1 ? 2 : 0);
  }
  if (current.length > 0 && segments.length < maxSegments) segments.push(current);
  const coveredTurns = segments.reduce((total, segment) => total + segment.length, 0);
  return { segments, coveredTurns, coversAll: coveredTurns === turns.length };
}
