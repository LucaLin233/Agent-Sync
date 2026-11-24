/**
 * Builds the bounded conversation excerpt sent to the title model.
 *
 * Only visible user and assistant text is considered: reasoning, tool calls,
 * notifications, todo/compaction records and plugin rows are dropped by the
 * caller. Obvious credentials are redacted here so they never reach the
 * helper session, an RPC reply, a log or a file.
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
  /** How many turns may be sampled across the whole session. */
  maxTurns?: number;
}

export interface ConversationExcerpt {
  text: string;
  turns: number;
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

interface TurnBucket {
  parts: string[];
}

const ROLE_LABEL: Readonly<Record<string, string>> = {
  user_message: "用户",
  assistant_message: "助手",
};

const USER_PREFIX = "用户：";

function lengthOf(value: string): number {
  return Array.from(value).length;
}

function turnText(turn: TurnBucket): string {
  return turn.parts.filter(Boolean).join("\n");
}

/**
 * A slot budget goes to the user's own question first and to the assistant's
 * answer only with the remainder, so one very long answer cannot hide the
 * question it answered.
 */
function blockFor(turn: TurnBucket, quota: number): string {
  if (quota <= 0) return "";
  const asked = turn.parts.filter((part) => part.startsWith(USER_PREFIX)).join("\n");
  const answered = turn.parts.filter((part) => !part.startsWith(USER_PREFIX)).join("\n");
  let block = "";
  if (asked) block = clip(asked, quota);
  if (answered) {
    const left = quota - lengthOf(block) - (block ? 2 : 0);
    if (left > 16) {
      const more = clip(answered, left);
      if (more) block = block ? `${block}\n${more}` : more;
    } else if (!block) {
      block = clip(answered, quota);
    }
  }
  return block;
}

/**
 * Adds the middle of the largest unselected gap while the budget can still pay
 * for it. Even sampling alone can step over a short but essential turn (one
 * message about the prompt rules, the next about the skill rules), and the
 * character budget, not a fixed turn count, is the real limit.
 */
function fillGaps(selected: number[], total: number, cost: (index: number) => number, budget: number): number[] {
  const chosen = new Set(selected);
  let used = selected.reduce((sum, index) => sum + cost(index), 0);
  for (;;) {
    const ordered = [...chosen].sort((left, right) => left - right);
    let bestGap: { middle: number; span: number } | null = null;
    for (let slot = 0; slot < ordered.length - 1; slot += 1) {
      const span = ordered[slot + 1] - ordered[slot];
      if (span < 2) continue;
      const middle = ordered[slot] + Math.floor(span / 2);
      if (!bestGap || span > bestGap.span) bestGap = { middle, span };
    }
    if (!bestGap) break;
    const extra = cost(bestGap.middle) + 2;
    if (used + extra > budget) break;
    chosen.add(bestGap.middle);
    used += extra;
  }
  return [...chosen].sort((left, right) => left - right);
}

/** Evenly spaced indexes over the whole range, always keeping both ends. */
function sampleIndices(total: number, limit: number): number[] {
  if (total <= limit) return Array.from({ length: total }, (_, index) => index);
  const picked: number[] = [];
  for (let slot = 0; slot < limit; slot += 1) {
    const index = Math.round((slot * (total - 1)) / (limit - 1));
    if (picked[picked.length - 1] !== index) picked.push(index);
  }
  return picked;
}

/**
 * Splits the character budget evenly across the selected turns, then lets the
 * leftovers of short turns flow to longer ones. Every evenly sampled period
 * keeps a share, so neither the opening nor the closing turns can take the
 * whole excerpt.
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
 * Builds a bounded excerpt that covers the session's opening, middle and end
 * rather than only the first task and the newest turns. Each selected period
 * keeps its own share of the budget, and a turn's user question is preferred
 * over its assistant answer.
 */
export function buildConversationExcerpt(
  entries: readonly ConversationEntry[],
  options: ExcerptOptions = {},
): ConversationExcerpt {
  const maxChars = options.maxChars ?? 2_400;
  const maxTurns = Math.max(3, options.maxTurns ?? 10);
  // Many selected turns must still fit the overall budget.
  const maxMessageChars = Math.min(options.maxMessageChars ?? 700, Math.floor(maxChars / 3));

  const turns: TurnBucket[] = [];
  const turnByIndex = new Map<string, TurnBucket>();
  let lastText = "";
  for (const entry of entries) {
    const label = ROLE_LABEL[entry.type];
    if (!label || typeof entry.text !== "string") continue;
    const cleaned = redactSecrets(normalize(withoutInjectedBlocks(entry.text)));
    if (!cleaned || cleaned === lastText) continue;
    lastText = cleaned;
    // A turn id groups a user message with the assistant replies it caused;
    // without one, each message is its own turn.
    const key = entry.turnId ? `turn:${entry.turnId}` : `message:${turns.length}`;
    let bucket = turnByIndex.get(key);
    if (!bucket) {
      bucket = { parts: [] };
      turnByIndex.set(key, bucket);
      turns.push(bucket);
    }
    bucket.parts.push(`${label}：${clip(cleaned, maxMessageChars)}`);
  }
  if (turns.length === 0) return { text: "", turns: 0 };

  // The extra two characters pay for the newline blockFor inserts between a
  // question and its answer; without them a short turn loses its answer.
  const sized = turns.map((turn) => Math.min(lengthOf(turnText(turn)) + 2, maxMessageChars * 2 + 2));
  const sampled = sampleIndices(turns.length, maxTurns);
  const selected = fillGaps(sampled, turns.length, (index) => sized[index], maxChars);
  const full = selected.map((index) => turnText(turns[index]));
  const sizes = selected.map((index) => sized[index]);
  const separators = 2 * Math.max(0, selected.length - 1);
  const budget = Math.max(0, maxChars - separators);
  // Leave a little room for the newline a user/assistant pair adds per block.
  const allocation = allocate(sizes, Math.max(0, budget - selected.length * 2));

  const blocks = full.map((_, position) => blockFor(turns[selected[position]], allocation[position]));
  let text = normalize(blocks.filter(Boolean).join("\n\n"));

  if (lengthOf(text) > maxChars) {
    // Proportional tightening keeps every period represented instead of
    // dropping the middle again.
    const scale = maxChars / Math.max(1, lengthOf(text));
    const tightened = blocks.map((block, position) =>
      block ? clip(block, Math.max(16, Math.floor(allocation[position] * scale))) : "",
    );
    text = normalize(tightened.filter(Boolean).join("\n\n"));
  }
  if (lengthOf(text) > maxChars) {
    text = Array.from(text).slice(0, maxChars).join("").trim();
  }
  const kept = blocks.filter(Boolean).length;
  return { text, turns: kept };
}
