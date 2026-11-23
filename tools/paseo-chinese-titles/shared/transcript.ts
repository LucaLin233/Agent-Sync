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
  /** First task plus this many of the newest turns. */
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

function lengthOf(value: string): number {
  return Array.from(value).length;
}

/**
 * Keeps the first task and the newest turns rather than the oldest middle, so
 * a long session is summarised by why it started and what is being discussed
 * now. Middle turns only fill leftover budget.
 */
export function buildConversationExcerpt(
  entries: readonly ConversationEntry[],
  options: ExcerptOptions = {},
): ConversationExcerpt {
  const maxChars = options.maxChars ?? 2_400;
  const maxTurns = Math.max(2, options.maxTurns ?? 6);
  // With many turns "first + newest" must still fit the overall budget.
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

  const turnText = (turn: TurnBucket) => turn.parts.filter(Boolean).join("\n");
  const first = turns[0];
  const rest = turns.slice(1);
  const recent = rest.slice(Math.max(0, rest.length - (maxTurns - 1)));

  // The first task is always present; the newest turn is preserved even when
  // the budget is tight. Remaining room then goes to newer middle turns.
  const firstBudget = Math.max(80, Math.min(maxMessageChars * 2, Math.floor(maxChars * 0.4)));
  const blocks: string[] = [clip(turnText(first), firstBudget)];

  const newest = recent[recent.length - 1];
  const reserveNewest = newest ? clip(turnText(newest), maxMessageChars) : "";

  const chosen: TurnBucket[] = [];
  let used = lengthOf(blocks[0]) + 2 + lengthOf(reserveNewest);
  for (let index = recent.length - 2; index >= 0; index -= 1) {
    const block = clip(turnText(recent[index]), maxMessageChars);
    if (!block) continue;
    if (used + 2 + lengthOf(block) > maxChars) continue;
    chosen.unshift(recent[index]);
    used += 2 + lengthOf(block);
  }

  const ordered = [...chosen, ...(newest ? [newest] : [])];
  const recentText = ordered.map(turnText).filter(Boolean).join("\n\n");
  let text = [blocks[0], recentText].filter(Boolean).join("\n\n");

  if (lengthOf(text) > maxChars) {
    // Hard fallback: keep the head of the first task and the tail of the
    // newest turn, never the middle of the session.
    const tail = clip(turnText(newest ?? first), Math.floor(maxChars / 2));
    const head = clip(turnText(first), Math.max(40, maxChars - lengthOf(tail) - 4));
    text = [head, tail].filter(Boolean).join("\n\n");
  }
  return { text: normalize(text), turns: ordered.length + 1 };
}
