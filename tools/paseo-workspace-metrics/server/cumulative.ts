import { constants, promises as fs, realpathSync } from "node:fs";
import type { FileHandle } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, isAbsolute, join, relative, resolve, sep } from "node:path";
import type { RpcInput, RpcOutput } from "@getpaseo/plugin";
import type { PluginHandlerContext } from "@getpaseo/plugin/server";
import type { cumulativeUsageRpc, turnOutputRpc } from "../shared/cumulative.ts";
import {
  addTurn,
  emptyTurnTotals,
  latestCompletedTurn,
  mergeTurnTotals,
  sessionKindOf,
  summarizeLatestSamples,
  type TurnTotals,
} from "../shared/metrics.ts";
import { effectiveWorkspaceScope, type WorkspaceSettingsValues } from "../shared/scope.ts";

export interface CodexHomeSettings {
  read(): Promise<
    | { status: "ready"; revision?: string; values: WorkspaceSettingsValues & { codexHome?: string; claudeHome?: string } }
    | { status: "invalid"; revision?: string; error: string }
  >;
}

interface SessionFile {
  path: string;
  dev: number;
  ino: number;
  size: number;
  mtimeMs: number;
  ctimeMs: number;
}

export interface CompletedTurn {
  /** The successful task_complete timestamp; the only ordering key for "latest". */
  completedAt: number;
  /** Cumulative output rose by this much between the turn's native boundaries. */
  outputTokens: number | null;
  /** Both boundaries come from the same rollout, never from client events. */
  elapsedMs: number | null;
  /** Codex's own time_to_first_token_ms for that completed turn, if reported. */
  firstTokenMs: number | null;
}

interface CacheCounts {
  input: number;
  cached: number;
}

interface SessionRead {
  sample: CacheCounts | null;
  /** Detail semantics: a failed or aborted turn clears this. */
  lastTurn: CompletedTurn | null;
  /** Latest successful turn; a later failure does not erase it. */
  lastSuccessful: CompletedTurn | null;
  /**
   * Completed turns read from this rollout, accumulated as observed. A later
   * rollback clears the visible latest turn and baseline, not this history.
   */
  turns: TurnTotals;
}

interface FileState {
  dev: number;
  ino: number;
  size: number;
  mtimeMs: number;
  ctimeMs: number;
  offset: number;
  valid: boolean;
  input: number;
  cached: number;
  trustedOutput: number | null;
  lastTurn: CompletedTurn | null;
  lastSuccessful: CompletedTurn | null;
  turns: TurnTotals;
  /** Bounded ids of turns already added; a replayed rollback turn stays out. */
  countedTurnIds: Set<string>;
  openTurn: {
    id: string;
    startedAt: number;
    baseline: number | null;
    finalAt: number | null;
    finalOutput: number | null;
    broken: boolean;
  } | null;
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const PATH_TTL_MS = 30_000;
const MAX_DIR_ENTRIES = 5_000;
const MAX_SESSION_BYTES = 256 * 1024 * 1024;
const READ_CHUNK_BYTES = 1024 * 1024;
const O_NOFOLLOW = constants.O_NOFOLLOW ?? 0;

const WORKSPACE_TTL_MS = 2_000;
const pathCache = new Map<string, { at: number; file: SessionFile | null }>();
const fileCache = new Map<string, FileState>();
const inflight = new Map<string, Promise<SessionRead | null>>();
const workspaceCache = new Map<string, { at: number; value: RpcOutput<typeof cumulativeUsageRpc> }>();
const workspaceInflight = new Map<string, Promise<RpcOutput<typeof cumulativeUsageRpc>>>();
let cacheGeneration = 0;

export function clearCumulativeCaches() {
  cacheGeneration += 1;
  pathCache.clear();
  fileCache.clear();
  inflight.clear();
  claudeFileCache.clear();
  claudeInflight.clear();
  clearCumulativeRequestCache();
}

/** Clears only the short same-workspace coalescing window. */
export function clearCumulativeRequestCache() {
  workspaceCache.clear();
  workspaceInflight.clear();
}

function isToken(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null ? value as Record<string, unknown> : null;
}

interface ProjectedEvent {
  eventType: string | null;
  payloadType: string | null;
  timestamp: string | null;
  turnId: string | null;
  firstTokenMs: number | null;
  errorPresent: boolean;
  input: number | null;
  cached: number | null;
  output: number | null;
  /** False when the top-level object did not close; partial records are ignored. */
  closed: boolean;
}

function emptyProjection(): ProjectedEvent {
  return {
    eventType: null, payloadType: null, timestamp: null, turnId: null,
    firstTokenMs: null, errorPresent: false, input: null, cached: null, output: null,
    closed: false,
  };
}

function skipSpace(raw: string, index: number): number {
  while (index < raw.length && (raw[index] === " " || raw[index] === "\t" || raw[index] === "\n" || raw[index] === "\r")) {
    index += 1;
  }
  return index;
}

function skipString(raw: string, index: number): number {
  let escaped = false;
  for (let cursor = index + 1; cursor < raw.length; cursor += 1) {
    const char = raw[cursor];
    if (escaped) escaped = false;
    else if (char === "\\") escaped = true;
    else if (char === '"') return cursor + 1;
  }
  return raw.length;
}

function skipValue(raw: string, index: number): number {
  index = skipSpace(raw, index);
  const first = raw[index];
  if (first === '"') return skipString(raw, index);
  if (first === "{" || first === "[") {
    const close = first === "{" ? "}" : "]";
    let depth = 0;
    let inString = false;
    let escaped = false;
    for (let cursor = index; cursor < raw.length; cursor += 1) {
      const char = raw[cursor];
      if (inString) {
        if (escaped) escaped = false;
        else if (char === "\\") escaped = true;
        else if (char === '"') inString = false;
        continue;
      }
      if (char === '"') inString = true;
      else if (char === first) depth += 1;
      else if (char === close) {
        depth -= 1;
        if (depth === 0) return cursor + 1;
      }
    }
    return raw.length;
  }
  while (index < raw.length && raw[index] !== "," && raw[index] !== "}" && raw[index] !== "]") index += 1;
  return index;
}

/** Reads a short string value; longer values are skipped and return null. */
function readSmallString(raw: string, index: number, max = 256): { value: string | null; end: number } {
  const end = skipString(raw, index);
  if (end - index - 2 > max) return { value: null, end };
  try {
    return { value: JSON.parse(raw.slice(index, end)) as string, end };
  } catch {
    return { value: null, end };
  }
}

function readSafeNumber(raw: string, index: number): { value: number | null; end: number } {
  const match = /^-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?/.exec(raw.slice(index, index + 32));
  if (!match) return { value: null, end: index };
  const end = index + match[0].length;
  const value = Number(match[0]);
  return { value: Number.isSafeInteger(value) && value >= 0 ? value : null, end };
}

function projectUsageFields(raw: string, index: number, out: ProjectedEvent): number {
  index = skipSpace(raw, index);
  if (raw[index] !== "{") return skipValue(raw, index);
  index += 1;
  while (index < raw.length) {
    index = skipSpace(raw, index);
    if (raw[index] === "}") return index + 1;
    if (raw[index] === ",") { index += 1; continue; }
    if (raw[index] !== '"') return skipValue(raw, index);
    const key = readSmallString(raw, index, 64);
    index = skipSpace(raw, key.end);
    if (raw[index] !== ":") return raw.length;
    index = skipSpace(raw, index + 1);
    if (key.value === "input_tokens") { const value = readSafeNumber(raw, index); out.input = value.value; index = value.end; }
    else if (key.value === "cached_input_tokens") { const value = readSafeNumber(raw, index); out.cached = value.value; index = value.end; }
    else if (key.value === "output_tokens") { const value = readSafeNumber(raw, index); out.output = value.value; index = value.end; }
    else index = skipValue(raw, index);
  }
  return raw.length;
}

function projectInfo(raw: string, index: number, out: ProjectedEvent): number {
  index = skipSpace(raw, index);
  if (raw[index] !== "{") return skipValue(raw, index);
  index += 1;
  while (index < raw.length) {
    index = skipSpace(raw, index);
    if (raw[index] === "}") return index + 1;
    if (raw[index] === ",") { index += 1; continue; }
    if (raw[index] !== '"') return skipValue(raw, index);
    const key = readSmallString(raw, index, 64);
    index = skipSpace(raw, key.end);
    if (raw[index] !== ":") return raw.length;
    index = skipSpace(raw, index + 1);
    index = key.value === "total_token_usage"
      ? projectUsageFields(raw, index, out)
      : skipValue(raw, index);
  }
  return raw.length;
}

function projectPayload(raw: string, index: number, out: ProjectedEvent): number {
  index = skipSpace(raw, index);
  if (raw[index] !== "{") return skipValue(raw, index);
  index += 1;
  while (index < raw.length) {
    index = skipSpace(raw, index);
    if (raw[index] === "}") return index + 1;
    if (raw[index] === ",") { index += 1; continue; }
    if (raw[index] !== '"') return skipValue(raw, index);
    const key = readSmallString(raw, index, 64);
    index = skipSpace(raw, key.end);
    if (raw[index] !== ":") return raw.length;
    index = skipSpace(raw, index + 1);
    if (key.value === "type") {
      const value = readSmallString(raw, index, 64);
      out.payloadType = value.value;
      index = value.end;
    } else if (key.value === "turn_id") {
      const value = readSmallString(raw, index, 128);
      out.turnId = value.value;
      index = value.end;
    } else if (key.value === "time_to_first_token_ms") {
      const value = readSafeNumber(raw, index);
      out.firstTokenMs = value.value;
      index = value.end;
    } else if (key.value === "error") {
      // Only presence matters; the nested error body is skipped, never parsed.
      const end = skipValue(raw, index);
      out.errorPresent = raw.slice(index, end).trim() !== "null";
      index = end;
    } else if (key.value === "info") {
      index = projectInfo(raw, index, out);
    } else {
      index = skipValue(raw, index);
    }
  }
  return raw.length;
}

/**
 * Structural projection of exactly the fields this reader uses. Strings and
 * nested values that are not on the whitelist are skipped, not parsed, so
 * assistant text and error bodies never enter the object graph. The top-level
 * event type is taken from the real envelope, not from a substring.
 */
export function projectEventLine(raw: string): ProjectedEvent {
  const out = emptyProjection();
  let index = skipSpace(raw, 0);
  if (raw[index] !== "{") return out;
  index += 1;
  while (index < raw.length) {
    index = skipSpace(raw, index);
    if (raw[index] === "}") { out.closed = true; break; }
    if (raw[index] === ",") { index += 1; continue; }
    if (raw[index] !== '"') return out;
    const key = readSmallString(raw, index, 64);
    index = skipSpace(raw, key.end);
    if (raw[index] !== ":") return out;
    index = skipSpace(raw, index + 1);
    if (key.value === "type") {
      const value = readSmallString(raw, index, 32);
      out.eventType = value.value ?? "";
      index = value.end;
    } else if (key.value === "timestamp") {
      const value = readSmallString(raw, index, 64);
      out.timestamp = value.value;
      index = value.end;
    } else if (key.value === "payload") {
      index = projectPayload(raw, index, out);
    } else {
      index = skipValue(raw, index);
    }
  }
  return out;
}

function parseLine(line: string, state: FileState) {
  if (!line.includes("event_msg")) return;
  const event = projectEventLine(line);
  if (!event.closed || event.eventType !== "event_msg") return;
  const at = event.timestamp === null ? NaN : Date.parse(event.timestamp);
  const type = event.payloadType;

  if (type === "task_started") {
    if (!event.turnId || !Number.isFinite(at)) return;
    const abandoned = state.openTurn !== null;
    const baseline = abandoned ? null : state.trustedOutput;
    if (abandoned) state.trustedOutput = null;
    state.openTurn = { id: event.turnId, startedAt: at, baseline, finalAt: null, finalOutput: null, broken: false };
    return;
  }

  if (type === "task_complete" || type === "turn_complete") {
    const open = state.openTurn;
    if (!event.turnId || !open || open.id !== event.turnId || !Number.isFinite(at)) return;
    state.openTurn = null;
    const firstTokenMs = event.firstTokenMs;
    if (event.errorPresent) {
      state.trustedOutput = null;
      state.lastTurn = null;
      return;
    }
    const finalTrusted = !open.broken && open.finalOutput !== null &&
      open.finalAt !== null && open.finalAt >= open.startedAt && open.finalAt <= at;
    const outputValid = finalTrusted && open.baseline !== null && open.finalOutput! >= open.baseline;
    state.trustedOutput = finalTrusted ? open.finalOutput : null;
    const turn: CompletedTurn = {
      completedAt: at,
      outputTokens: outputValid ? open.finalOutput! - open.baseline! : null,
      elapsedMs: at >= open.startedAt ? at - open.startedAt : null,
      firstTokenMs,
    };
    // The detail follows the file's event order, so a replayed turn replaces
    // the terminal measurement it re-describes.
    state.lastTurn = turn;
    // A turn replayed after a rollback is not a second observation: it neither
    // adds to the cumulative sums nor restores the overview's success turn.
    if (state.countedTurnIds.has(event.turnId)) return;
    state.countedTurnIds.add(event.turnId);
    if (state.countedTurnIds.size > 64) {
      const oldest = state.countedTurnIds.values().next().value;
      if (oldest !== undefined) state.countedTurnIds.delete(oldest);
    }
    if (state.lastSuccessful === null || turn.completedAt > state.lastSuccessful.completedAt) {
      state.lastSuccessful = turn;
    }
    state.turns = addTurn(state.turns, turn);
    return;
  }

  if (type === "turn_aborted") {
    // Canceled work clears the detail's terminal turn but is not a completed
    // observation: the overview keeps the last successful turn.
    state.openTurn = null;
    state.lastTurn = null;
    state.trustedOutput = null;
    return;
  }

  if (type === "thread_rolled_back") {
    // A rollback erases the turn it rewinds, including the successful result.
    state.openTurn = null;
    state.lastTurn = null;
    state.lastSuccessful = null;
    state.trustedOutput = null;
    return;
  }

  if (type !== "token_count") return;
  const input = event.input;
  const cached = event.cached;
  const output = event.output;
  // A bad cache sample never discards the last valid cache counters.
  if (input !== null && cached !== null && cached <= input) {
    state.input = input;
    state.cached = cached;
    state.valid = true;
  }
  if (output === null || !Number.isFinite(at)) {
    if (state.openTurn) state.openTurn.broken = true;
    return;
  }
  const open = state.openTurn;
  if (!open) {
    // A valid count between turns means the last completed boundary is no
    // longer the value the next turn starts from. Any change invalidates it,
    // not only a smaller one.
    if (state.trustedOutput !== null && output !== state.trustedOutput) {
      state.trustedOutput = null;
    }
    return;
  }
  {
    if (at < open.startedAt || (open.finalAt !== null && at < open.finalAt)) {
      open.broken = true;
    } else if (
      (open.finalOutput !== null && output < open.finalOutput) ||
      (open.baseline !== null && output < open.baseline)
    ) {
      open.broken = true;
    } else {
      open.finalAt = at;
      open.finalOutput = output;
    }
  }
}

function resetState(file: { dev: number; ino: number; size: number; mtimeMs: number; ctimeMs: number }): FileState {
  return {
    dev: file.dev,
    ino: file.ino,
    size: file.size,
    mtimeMs: file.mtimeMs,
    ctimeMs: file.ctimeMs,
    offset: 0,
    input: 0,
    cached: 0,
    lastTurn: null,
    lastSuccessful: null,
    turns: emptyTurnTotals(),
    countedTurnIds: new Set(),
    valid: false,
    trustedOutput: null,
    openTurn: null,
  };
}

function sameFile(a: { dev: number; ino: number }, b: { dev: number; ino: number }) {
  return a.dev === b.dev && a.ino === b.ino;
}

function sameState(a: FileState, b: { dev: number; ino: number; size: number; mtimeMs: number; ctimeMs: number }) {
  return a.dev === b.dev && a.ino === b.ino && a.size === b.size &&
    a.mtimeMs === b.mtimeMs && a.ctimeMs === b.ctimeMs;
}

function countsOf(state: FileState): SessionRead {
  return {
    sample: state.valid ? { input: state.input, cached: state.cached } : null,
    lastTurn: state.lastTurn,
    lastSuccessful: state.lastSuccessful,
    turns: state.turns,
  };
}

async function appendFromHandle(handle: FileHandle, state: FileState, end: number) {
  let pending: Buffer = Buffer.alloc(0);
  let position = state.offset;
  while (position < end) {
    const length = Math.min(READ_CHUNK_BYTES, end - position);
    const buffer = Buffer.allocUnsafe(length);
    const { bytesRead } = await handle.read(buffer, 0, length, position);
    if (bytesRead <= 0) break;
    position += bytesRead;
    pending = pending.length === 0 ? buffer.subarray(0, bytesRead) : Buffer.concat([pending, buffer.subarray(0, bytesRead)]);
    let newline = pending.indexOf(0x0a);
    while (newline !== -1) {
      parseLine(pending.subarray(0, newline).toString("utf8"), state);
      pending = pending.subarray(newline + 1);
      newline = pending.indexOf(0x0a);
    }
  }
  // Re-read an unterminated tail on the next call instead of dropping it.
  state.offset = position - pending.length;
}

function forget(path: string) {
  fileCache.delete(path);
  for (const [key, entry] of pathCache) {
    if (entry.file?.path === path) pathCache.delete(key);
  }
}

async function readSessionCountsUncached(file: SessionFile): Promise<SessionRead | null> {
  let before;
  try {
    before = await fs.lstat(file.path);
  } catch {
    forget(file.path);
    return null;
  }
  if (!before.isFile() || before.isSymbolicLink() || !sameFile(file, before)) {
    forget(file.path);
    return null;
  }

  let handle: FileHandle | null = null;
  try {
    handle = await fs.open(file.path, constants.O_RDONLY | O_NOFOLLOW);
    const stat = await handle.stat();
    if (!stat.isFile() || !sameFile(file, stat)) {
      forget(file.path);
      return null;
    }
    if (stat.size > MAX_SESSION_BYTES) return null;

    let state = fileCache.get(file.path);
    if (state && sameState(state, stat)) {
      return countsOf(state);
    }
    if (!state || !sameFile(state, stat) || stat.size < state.offset) {
      state = resetState(stat);
    } else if (stat.size === state.size && (state.mtimeMs !== stat.mtimeMs || state.ctimeMs !== stat.ctimeMs)) {
      // A same-length in-place replacement must be parsed again.
      state = resetState(stat);
    } else {
      state.size = stat.size;
      state.mtimeMs = stat.mtimeMs;
      state.ctimeMs = stat.ctimeMs;
    }

    await appendFromHandle(handle, state, stat.size);
    state.size = stat.size;
    state.mtimeMs = stat.mtimeMs;
    state.ctimeMs = stat.ctimeMs;
    fileCache.set(file.path, state);
    return countsOf(state);
  } catch {
    forget(file.path);
    return null;
  } finally {
    if (handle) await handle.close().catch(() => undefined);
  }
}

function readSessionCounts(file: SessionFile): Promise<SessionRead | null> {
  const key = `${file.path}|${file.dev}|${file.ino}|${file.size}|${file.mtimeMs}|${file.ctimeMs}`;
  const running = inflight.get(key);
  if (running) return running;
  const task = readSessionCountsUncached(file).finally(() => inflight.delete(key));
  inflight.set(key, task);
  return task;
}

function pickBest(files: SessionFile[]): SessionFile | null {
  let best: SessionFile | null = null;
  for (const file of files) {
    if (!best || file.size > best.size || (file.size === best.size && file.mtimeMs > best.mtimeMs)) best = file;
  }
  return best;
}

async function listExact(dir: string, uuid: string): Promise<SessionFile[]> {
  let dirStat;
  try {
    dirStat = await fs.lstat(dir);
  } catch {
    return [];
  }
  if (!dirStat.isDirectory() || dirStat.isSymbolicLink()) return [];
  let entries;
  try {
    entries = await fs.readdir(dir, { withFileTypes: true });
  } catch {
    return [];
  }
  const result: SessionFile[] = [];
  let visited = 0;
  for (const entry of entries) {
    if (++visited > MAX_DIR_ENTRIES) break;
    if (entry.isSymbolicLink() || !entry.isFile()) continue;
    if (!entry.name.toLowerCase().endsWith(`-${uuid}.jsonl`)) continue;
    const full = join(dir, entry.name);
    let stat;
    try {
      stat = await fs.lstat(full);
    } catch {
      continue;
    }
    if (!stat.isFile() || stat.isSymbolicLink()) continue;
    result.push({
      path: full,
      dev: stat.dev,
      ino: stat.ino,
      size: stat.size,
      mtimeMs: stat.mtimeMs,
      ctimeMs: stat.ctimeMs,
    });
  }
  return result;
}

async function existingDateDir(root: string, key: string): Promise<string | null> {
  let dir = root;
  for (const part of ["sessions", ...key.split("/")]) {
    dir = join(dir, part);
    let stat;
    try {
      stat = await fs.lstat(dir);
    } catch {
      return null;
    }
    if (!stat.isDirectory() || stat.isSymbolicLink()) return null;
  }
  return dir;
}

function uuidV7Millis(uuid: string): number | null {
  if (uuid.charAt(14) !== "7") return null;
  const millis = parseInt(uuid.slice(0, 8) + uuid.slice(9, 13), 16);
  if (!Number.isSafeInteger(millis) || millis < Date.UTC(2020, 0, 1) || millis > Date.UTC(2100, 0, 1)) return null;
  return millis;
}

function dateKeys(millis: number): string[] {
  const keys: string[] = [];
  for (const delta of [-86_400_000, 0, 86_400_000]) {
    const date = new Date(millis + delta);
    if (!Number.isFinite(date.getTime())) continue;
    const year = String(date.getUTCFullYear());
    const month = String(date.getUTCMonth() + 1).padStart(2, "0");
    const day = String(date.getUTCDate()).padStart(2, "0");
    keys.push(`${year}/${month}/${day}`);
  }
  return keys;
}

async function findSessionFile(
  root: string,
  uuid: string,
  createdMs: number | null,
  refresh = false,
): Promise<SessionFile | null> {
  const key = `${root}|${uuid}|${createdMs ?? ""}`;
  const cached = pathCache.get(key);
  // A refresh ignores a cached miss so a rollout that just appeared is found.
  if (cached && Date.now() - cached.at < PATH_TTL_MS && (cached.file !== null || !refresh)) {
    return cached.file;
  }

  const candidates = await listExact(join(root, "archived_sessions"), uuid);
  const dates = new Set<string>();
  const v7 = uuidV7Millis(uuid);
  if (v7 !== null) for (const date of dateKeys(v7)) dates.add(date);
  if (createdMs !== null && Number.isFinite(createdMs)) for (const date of dateKeys(createdMs)) dates.add(date);
  for (const date of dates) {
    const dir = await existingDateDir(root, date);
    if (dir) candidates.push(...await listExact(dir, uuid));
  }

  const best = pickBest(candidates);
  if (best) {
    try {
      const real = await fs.realpath(best.path);
      if (!real.startsWith(root + sep)) {
        pathCache.set(key, { at: Date.now(), file: null });
        return null;
      }
    } catch {
      if (!refresh) pathCache.set(key, { at: Date.now(), file: null });
      return null;
    }
  }
  if (best || !refresh) pathCache.set(key, { at: Date.now(), file: best });
  return best;
}

// ---------------------------------------------------------------------------
// Claude Code transcripts
//
// Claude Code keeps one JSONL transcript per session at
// <claude home>/projects/<encoded cwd>/<sessionId>.jsonl, where the claude home
// is CLAUDE_CONFIG_DIR or ~/.claude. Each API response is an `assistant` record
// whose message carries that request's usage. A response split into several
// content blocks is written as several records with the same message id and the
// same usage, so a message counts once. The session's totals are the sum over
// its requests; the input total includes cache writes and cache reads, which
// matches Codex's input_tokens (cache reads included) as the rate denominator.
//
// Turns: a main-chain user record carrying a text block (not a tool result,
// not meta) starts a turn; the last record of the main-chain assistant message
// whose stop_reason is end_turn closes it. The turn's output is the sum of its
// messages' output_tokens. A new prompt before end_turn abandons the open turn;
// a synthetic API-error message fails it. Claude does not record a provider
// first-token time, so that stays null.
// ---------------------------------------------------------------------------

interface ClaudeOpenTurn {
  id: string;
  startedAt: number;
  output: number;
  broken: boolean;
  /** end_turn message seen; later records of the same message move the end. */
  endMessageId: string | null;
  endAt: number | null;
}

interface ClaudeFileState {
  dev: number;
  ino: number;
  size: number;
  mtimeMs: number;
  ctimeMs: number;
  offset: number;
  input: number;
  cached: number;
  requests: number;
  /** The newest main-chain request, the Claude counterpart of Codex's latest sample. */
  latest: CacheCounts | null;
  /** Bounded recent message ids; repeated content-block records stay out. */
  seen: Set<string>;
  openTurn: ClaudeOpenTurn | null;
  lastTurn: CompletedTurn | null;
  lastSuccessful: CompletedTurn | null;
  turns: TurnTotals;
  countedTurnIds: Set<string>;
}

export interface ClaudeRead {
  sample: CacheCounts | null;
  latest: CacheCounts | null;
  lastTurn: CompletedTurn | null;
  lastSuccessful: CompletedTurn | null;
  turns: TurnTotals;
}

interface ClaudeProjection {
  eventType: string | null;
  timestamp: string | null;
  uuid: string | null;
  sidechain: boolean;
  meta: boolean;
  apiError: boolean;
  messageId: string | null;
  stopReason: string | null;
  /** The content's block types; a plain string content counts as "text". */
  contentTypes: string[];
  input: number | null;
  cacheCreation: number | null;
  cacheRead: number | null;
  output: number | null;
  closed: boolean;
}

const CLAUDE_SEEN_LIMIT = 512;
const claudeFileCache = new Map<string, ClaudeFileState>();
const claudeInflight = new Map<string, Promise<ClaudeRead | null>>();

function projectClaudeUsage(raw: string, index: number, out: ClaudeProjection): number {
  index = skipSpace(raw, index);
  if (raw[index] !== "{") return skipValue(raw, index);
  index += 1;
  while (index < raw.length) {
    index = skipSpace(raw, index);
    if (raw[index] === "}") return index + 1;
    if (raw[index] === ",") { index += 1; continue; }
    if (raw[index] !== '"') return skipValue(raw, index);
    const key = readSmallString(raw, index, 64);
    index = skipSpace(raw, key.end);
    if (raw[index] !== ":") return raw.length;
    index = skipSpace(raw, index + 1);
    if (key.value === "input_tokens") { const value = readSafeNumber(raw, index); out.input = value.value; index = value.end; }
    else if (key.value === "cache_creation_input_tokens") { const value = readSafeNumber(raw, index); out.cacheCreation = value.value; index = value.end; }
    else if (key.value === "cache_read_input_tokens") { const value = readSafeNumber(raw, index); out.cacheRead = value.value; index = value.end; }
    else if (key.value === "output_tokens") { const value = readSafeNumber(raw, index); out.output = value.value; index = value.end; }
    else index = skipValue(raw, index);
  }
  return raw.length;
}

/** Reads only each content block's `type`; text and inputs are skipped. */
function projectClaudeContent(raw: string, index: number, out: ClaudeProjection): number {
  index = skipSpace(raw, index);
  if (raw[index] === '"') {
    out.contentTypes.push("text");
    return skipString(raw, index);
  }
  if (raw[index] !== "[") return skipValue(raw, index);
  index += 1;
  while (index < raw.length) {
    index = skipSpace(raw, index);
    if (raw[index] === "]") return index + 1;
    if (raw[index] === ",") { index += 1; continue; }
    if (raw[index] !== "{") { index = skipValue(raw, index); continue; }
    index += 1;
    while (index < raw.length) {
      index = skipSpace(raw, index);
      if (raw[index] === "}") { index += 1; break; }
      if (raw[index] === ",") { index += 1; continue; }
      if (raw[index] !== '"') return raw.length;
      const key = readSmallString(raw, index, 64);
      index = skipSpace(raw, key.end);
      if (raw[index] !== ":") return raw.length;
      index = skipSpace(raw, index + 1);
      if (key.value === "type") {
        const value = readSmallString(raw, index, 64);
        if (value.value) out.contentTypes.push(value.value);
        index = value.end;
      } else {
        index = skipValue(raw, index);
      }
    }
  }
  return raw.length;
}

function projectClaudeMessage(raw: string, index: number, out: ClaudeProjection): number {
  index = skipSpace(raw, index);
  if (raw[index] !== "{") return skipValue(raw, index);
  index += 1;
  while (index < raw.length) {
    index = skipSpace(raw, index);
    if (raw[index] === "}") return index + 1;
    if (raw[index] === ",") { index += 1; continue; }
    if (raw[index] !== '"') return skipValue(raw, index);
    const key = readSmallString(raw, index, 64);
    index = skipSpace(raw, key.end);
    if (raw[index] !== ":") return raw.length;
    index = skipSpace(raw, index + 1);
    if (key.value === "id") {
      const value = readSmallString(raw, index, 128);
      out.messageId = value.value;
      index = value.end;
    } else if (key.value === "stop_reason") {
      if (raw[index] === '"') {
        const value = readSmallString(raw, index, 64);
        out.stopReason = value.value;
        index = value.end;
      } else {
        index = skipValue(raw, index);
      }
    } else if (key.value === "content") {
      index = projectClaudeContent(raw, index, out);
    } else if (key.value === "usage") {
      index = projectClaudeUsage(raw, index, out);
    } else {
      index = skipValue(raw, index);
    }
  }
  return raw.length;
}

function readLiteralTrue(raw: string, index: number): { value: boolean; end: number } {
  const end = skipValue(raw, index);
  return { value: raw.slice(index, end).trim() === "true", end };
}

/**
 * Structural projection of a Claude transcript record: the envelope fields,
 * the message id and stop reason, content block types, and the usage counters.
 * Message text, tool inputs and results are skipped, never parsed.
 */
export function projectClaudeLine(raw: string): ClaudeProjection {
  const out: ClaudeProjection = {
    eventType: null, timestamp: null, uuid: null, sidechain: false, meta: false, apiError: false,
    messageId: null, stopReason: null, contentTypes: [],
    input: null, cacheCreation: null, cacheRead: null, output: null, closed: false,
  };
  let index = skipSpace(raw, 0);
  if (raw[index] !== "{") return out;
  index += 1;
  while (index < raw.length) {
    index = skipSpace(raw, index);
    if (raw[index] === "}") { out.closed = true; break; }
    if (raw[index] === ",") { index += 1; continue; }
    if (raw[index] !== '"') return out;
    const key = readSmallString(raw, index, 64);
    index = skipSpace(raw, key.end);
    if (raw[index] !== ":") return out;
    index = skipSpace(raw, index + 1);
    if (key.value === "type") {
      const value = readSmallString(raw, index, 32);
      out.eventType = value.value ?? "";
      index = value.end;
    } else if (key.value === "timestamp") {
      const value = readSmallString(raw, index, 64);
      out.timestamp = value.value;
      index = value.end;
    } else if (key.value === "uuid") {
      const value = readSmallString(raw, index, 128);
      out.uuid = value.value;
      index = value.end;
    } else if (key.value === "isSidechain") {
      const value = readLiteralTrue(raw, index); out.sidechain = value.value; index = value.end;
    } else if (key.value === "isMeta") {
      const value = readLiteralTrue(raw, index); out.meta = value.value; index = value.end;
    } else if (key.value === "isApiErrorMessage") {
      const value = readLiteralTrue(raw, index); out.apiError = value.value; index = value.end;
    } else if (key.value === "message") {
      index = projectClaudeMessage(raw, index, out);
    } else {
      index = skipValue(raw, index);
    }
  }
  return out;
}

function claudeTurnFrom(open: ClaudeOpenTurn): CompletedTurn | null {
  if (open.endAt === null) return null;
  return {
    completedAt: open.endAt,
    outputTokens: open.broken ? null : open.output,
    elapsedMs: open.endAt >= open.startedAt ? open.endAt - open.startedAt : null,
    firstTokenMs: null,
  };
}

/** Folds a finished turn into the session's observations, once per prompt id. */
function commitClaudeTurn(state: ClaudeFileState, open: ClaudeOpenTurn) {
  const turn = claudeTurnFrom(open);
  if (!turn) return;
  state.lastTurn = turn;
  if (state.countedTurnIds.has(open.id)) return;
  state.countedTurnIds.add(open.id);
  if (state.countedTurnIds.size > 64) {
    const oldest = state.countedTurnIds.values().next().value;
    if (oldest !== undefined) state.countedTurnIds.delete(oldest);
  }
  if (state.lastSuccessful === null || turn.completedAt > state.lastSuccessful.completedAt) {
    state.lastSuccessful = turn;
  }
  state.turns = addTurn(state.turns, turn);
}

function parseClaudeLine(line: string, state: ClaudeFileState) {
  if (!line.includes('"assistant"') && !line.includes('"user"')) return;
  const event = projectClaudeLine(line);
  if (!event.closed) return;
  const at = event.timestamp === null ? NaN : Date.parse(event.timestamp);

  if (event.eventType === "user") {
    if (event.sidechain || event.meta) return;
    if (event.contentTypes.includes("tool_result") || !event.contentTypes.includes("text")) return;
    if (!event.uuid || !Number.isFinite(at)) return;
    // A new prompt closes a turn that already reached end_turn and abandons one that did not.
    if (state.openTurn?.endMessageId) commitClaudeTurn(state, state.openTurn);
    state.openTurn = { id: event.uuid, startedAt: at, output: 0, broken: false, endMessageId: null, endAt: null };
    return;
  }

  if (event.eventType !== "assistant") return;
  const open = event.sidechain ? null : state.openTurn;

  if (event.apiError && !event.sidechain) {
    // The turn ended on an API error: it is not a completed observation.
    state.openTurn = null;
    state.lastTurn = null;
    return;
  }

  // Later records of the end_turn message move the turn's end, nothing else.
  if (open && open.endMessageId !== null && event.messageId === open.endMessageId) {
    if (Number.isFinite(at) && open.endAt !== null && at > open.endAt) open.endAt = at;
    return;
  }

  if (event.input === null) return;
  if (event.messageId) {
    if (state.seen.has(event.messageId)) return;
    state.seen.add(event.messageId);
    if (state.seen.size > CLAUDE_SEEN_LIMIT) {
      const oldest = state.seen.values().next().value;
      if (oldest !== undefined) state.seen.delete(oldest);
    }
  }
  const creation = event.cacheCreation ?? 0;
  const read = event.cacheRead ?? 0;
  const request = event.input + creation + read;
  const input = state.input + request;
  const cached = state.cached + read;
  if (!Number.isSafeInteger(input) || !Number.isSafeInteger(cached)) return;
  state.input = input;
  state.cached = cached;
  state.requests += 1;
  if (event.sidechain) return;
  if (request > 0) state.latest = { input: request, cached: read };

  if (!open) return;
  // Another request after end_turn means the turn continued (for example, a stop hook).
  if (open.endMessageId !== null) {
    open.endMessageId = null;
    open.endAt = null;
  }
  if (event.output === null) open.broken = true;
  else open.output += event.output;
  if (!Number.isFinite(at) || at < open.startedAt) open.broken = true;
  if (event.stopReason === "end_turn" && event.messageId && Number.isFinite(at) && at >= open.startedAt) {
    open.endMessageId = event.messageId;
    open.endAt = at;
  }
}

function resetClaudeState(file: { dev: number; ino: number; size: number; mtimeMs: number; ctimeMs: number }): ClaudeFileState {
  return {
    dev: file.dev, ino: file.ino, size: file.size, mtimeMs: file.mtimeMs, ctimeMs: file.ctimeMs,
    offset: 0, input: 0, cached: 0, requests: 0, latest: null, seen: new Set(),
    openTurn: null, lastTurn: null, lastSuccessful: null, turns: emptyTurnTotals(), countedTurnIds: new Set(),
  };
}

/**
 * A turn that reached end_turn is reported as completed at read time without
 * being folded into the state, so a later record that continues it, or a later
 * read, never counts it twice.
 */
function claudeCounts(state: ClaudeFileState): ClaudeRead {
  const sample = state.requests > 0 && state.input > 0 ? { input: state.input, cached: state.cached } : null;
  const open = state.openTurn;
  const pending = open && open.endMessageId !== null ? claudeTurnFrom(open) : null;
  if (!pending || !open) {
    return { sample, latest: state.latest, lastTurn: state.lastTurn, lastSuccessful: state.lastSuccessful, turns: state.turns };
  }
  const counted = state.countedTurnIds.has(open.id);
  return {
    sample,
    latest: state.latest,
    lastTurn: pending,
    lastSuccessful: counted || (state.lastSuccessful && state.lastSuccessful.completedAt >= pending.completedAt)
      ? state.lastSuccessful
      : pending,
    turns: counted ? state.turns : addTurn(state.turns, pending),
  };
}

async function appendClaudeFromHandle(handle: FileHandle, state: ClaudeFileState, end: number) {
  let pending: Buffer = Buffer.alloc(0);
  let position = state.offset;
  while (position < end) {
    const length = Math.min(READ_CHUNK_BYTES, end - position);
    const buffer = Buffer.allocUnsafe(length);
    const { bytesRead } = await handle.read(buffer, 0, length, position);
    if (bytesRead <= 0) break;
    position += bytesRead;
    pending = pending.length === 0 ? buffer.subarray(0, bytesRead) : Buffer.concat([pending, buffer.subarray(0, bytesRead)]);
    let newline = pending.indexOf(0x0a);
    while (newline !== -1) {
      parseClaudeLine(pending.subarray(0, newline).toString("utf8"), state);
      pending = pending.subarray(newline + 1);
      newline = pending.indexOf(0x0a);
    }
  }
  state.offset = position - pending.length;
}

function forgetClaude(path: string) {
  claudeFileCache.delete(path);
  for (const [key, entry] of pathCache) {
    if (entry.file?.path === path) pathCache.delete(key);
  }
}

async function readClaudeCountsUncached(file: SessionFile): Promise<ClaudeRead | null> {
  let before;
  try {
    before = await fs.lstat(file.path);
  } catch {
    forgetClaude(file.path);
    return null;
  }
  if (!before.isFile() || before.isSymbolicLink() || !sameFile(file, before)) {
    forgetClaude(file.path);
    return null;
  }
  let handle: FileHandle | null = null;
  try {
    handle = await fs.open(file.path, constants.O_RDONLY | O_NOFOLLOW);
    const stat = await handle.stat();
    if (!stat.isFile() || !sameFile(file, stat)) {
      forgetClaude(file.path);
      return null;
    }
    if (stat.size > MAX_SESSION_BYTES) return null;
    let state = claudeFileCache.get(file.path);
    if (state && state.dev === stat.dev && state.ino === stat.ino && state.size === stat.size &&
      state.mtimeMs === stat.mtimeMs && state.ctimeMs === stat.ctimeMs) {
      return claudeCounts(state);
    }
    if (!state || !sameFile(state, stat) || stat.size < state.offset ||
      (stat.size === state.size && (state.mtimeMs !== stat.mtimeMs || state.ctimeMs !== stat.ctimeMs))) {
      state = resetClaudeState(stat);
    }
    await appendClaudeFromHandle(handle, state, stat.size);
    state.size = stat.size;
    state.mtimeMs = stat.mtimeMs;
    state.ctimeMs = stat.ctimeMs;
    claudeFileCache.set(file.path, state);
    return claudeCounts(state);
  } catch {
    forgetClaude(file.path);
    return null;
  } finally {
    if (handle) await handle.close().catch(() => undefined);
  }
}

function readClaudeCounts(file: SessionFile): Promise<ClaudeRead | null> {
  const key = `${file.path}|${file.dev}|${file.ino}|${file.size}|${file.mtimeMs}|${file.ctimeMs}`;
  const running = claudeInflight.get(key);
  if (running) return running;
  const task = readClaudeCountsUncached(file).finally(() => claudeInflight.delete(key));
  claudeInflight.set(key, task);
  return task;
}

/** Same project-directory encoding as the Claude Agent SDK (and Paseo's port of it). */
export function claudeProjectDirName(cwd: string): string {
  let canonical = cwd;
  try {
    canonical = realpathSync.native(cwd);
  } catch {
    // A missing cwd is encoded as given.
  }
  if (process.platform === "darwin") canonical = canonical.normalize("NFC");
  const replaced = canonical.replace(/[^a-zA-Z0-9]/g, "-");
  if (replaced.length <= 200) return replaced;
  let hash = 0;
  for (let i = 0; i < canonical.length; i += 1) hash = ((hash << 5) - hash + canonical.charCodeAt(i)) | 0;
  return `${replaced.slice(0, 200)}-${Math.abs(hash).toString(36)}`;
}

async function plainDir(path: string): Promise<boolean> {
  try {
    const stat = await fs.lstat(path);
    return stat.isDirectory() && !stat.isSymbolicLink();
  } catch {
    return false;
  }
}

async function plainFile(path: string): Promise<SessionFile | null> {
  try {
    const stat = await fs.lstat(path);
    if (!stat.isFile() || stat.isSymbolicLink()) return null;
    return { path, dev: stat.dev, ino: stat.ino, size: stat.size, mtimeMs: stat.mtimeMs, ctimeMs: stat.ctimeMs };
  } catch {
    return null;
  }
}

/**
 * The transcript for one Claude session. The cwd's encoded project directory is
 * tried first; a session resumed elsewhere, or a cwd Claude saw under another
 * name, is found by a bounded scan of the project directories, as Paseo does.
 */
async function findClaudeTranscript(
  root: string,
  uuid: string,
  cwd: string | null,
  refresh = false,
): Promise<SessionFile | null> {
  const key = `claude|${root}|${uuid}|${cwd ?? ""}`;
  const cached = pathCache.get(key);
  if (cached && Date.now() - cached.at < PATH_TTL_MS && (cached.file !== null || !refresh)) {
    return cached.file;
  }
  const projects = join(root, "projects");
  const name = `${uuid}.jsonl`;
  let found: SessionFile | null = null;
  if (await plainDir(projects)) {
    if (cwd) {
      const dir = join(projects, claudeProjectDirName(cwd));
      if (await plainDir(dir)) found = await plainFile(join(dir, name));
    }
    if (!found) {
      let entries: import("node:fs").Dirent[] = [];
      try {
        entries = await fs.readdir(projects, { withFileTypes: true });
      } catch {
        entries = [];
      }
      let visited = 0;
      for (const entry of entries) {
        if (++visited > MAX_DIR_ENTRIES) break;
        if (entry.isSymbolicLink() || !entry.isDirectory()) continue;
        found = await plainFile(join(projects, entry.name, name));
        if (found) break;
      }
    }
  }
  if (found) {
    try {
      const real = await fs.realpath(found.path);
      if (!real.startsWith(root + sep)) found = null;
    } catch {
      found = null;
    }
  }
  if (found || !refresh) pathCache.set(key, { at: Date.now(), file: found });
  return found;
}

async function usableClaudeRoot(root: string): Promise<boolean> {
  try {
    const stat = await fs.stat(root);
    return stat.isDirectory() && await plainDir(join(root, "projects"));
  } catch {
    return false;
  }
}

/**
 * Claude home: an explicit plugin setting (inside the daemon user's home, no
 * fallback when invalid), then the daemon's CLAUDE_CONFIG_DIR, then ~/.claude.
 */
export async function resolveClaudeHomeFromValues(
  values: { claudeHome?: string },
  options: { home?: string; env?: string | null } = {},
): Promise<{ root: string | null; error: string | null }> {
  const home = resolve(options.home ?? homedir());
  let homeReal = home;
  try {
    homeReal = realpathSync(home);
  } catch {
    // A missing home can still be compared lexically.
  }
  const inside = (root: string) => {
    const rel = relative(homeReal, root);
    return !(rel === ".." || rel.startsWith(".." + sep) || isAbsolute(rel));
  };

  if (values.claudeHome) {
    if (!isAbsolute(values.claudeHome)) {
      return { root: null, error: "手动配置的 Claude home 必须是绝对路径" };
    }
    let root: string;
    try {
      root = realpathSync(resolve(values.claudeHome));
    } catch {
      return { root: null, error: "手动配置的 Claude home 不存在或不可读" };
    }
    if (!inside(root)) {
      return { root: null, error: "手动配置的 Claude home 必须位于 daemon 用户家目录内" };
    }
    if (!await usableClaudeRoot(root)) {
      return { root: null, error: "手动配置的 Claude home 下没有可用的 projects/ 目录" };
    }
    return { root, error: null };
  }

  const rawEnv = options.env === undefined ? process.env.CLAUDE_CONFIG_DIR : options.env;
  const env = rawEnv?.trim();
  if (env && isAbsolute(env)) {
    try {
      const root = realpathSync(resolve(env));
      if (await usableClaudeRoot(root)) return { root, error: null };
    } catch {
      // Fall back to the default Claude home.
    }
  }

  let root: string;
  try {
    root = realpathSync(join(home, ".claude"));
  } catch {
    return { root: null, error: "未找到 Claude 会话目录；请设置 CLAUDE_CONFIG_DIR 或插件 claudeHome" };
  }
  if (!inside(root)) return { root: null, error: "默认 Claude home 不在 daemon 用户家目录内" };
  if (await usableClaudeRoot(root)) return { root, error: null };
  return { root: null, error: "未找到 Claude 会话目录；请设置 CLAUDE_CONFIG_DIR 或插件 claudeHome" };
}

type HomeValues = WorkspaceSettingsValues & { codexHome?: string; claudeHome?: string };

interface SettingsSnapshot {
  values: HomeValues;
  revision: string | null;
}

async function readSettingsSnapshot(settings?: CodexHomeSettings): Promise<SettingsSnapshot> {
  if (!settings) return { values: {}, revision: null };
  try {
    const state = await settings.read();
    if (state.status === "ready") return { values: state.values, revision: state.revision ?? null };
    return { values: {}, revision: state.revision ?? null };
  } catch {
    // An unreadable setting means no scope; never widen the default.
  }
  return { values: {}, revision: null };
}

/** True when the stored settings moved on during this request's async work. */
async function settingsChangedSince(settings: CodexHomeSettings | undefined, revision: string | null): Promise<boolean> {
  if (!settings || revision === null) return false;
  try {
    const state = await settings.read();
    return state.revision !== revision;
  } catch {
    return true;
  }
}

export async function workspaceScope(settings?: CodexHomeSettings) {
  const { values } = await readSettingsSnapshot(settings);
  const scope = effectiveWorkspaceScope(values);
  return {
    enabled: scope.enabled,
    workspaceIds: scope.workspaceIds,
    allWorkspaces: scope.allWorkspaces,
    codexHomeConfigured: Boolean(values.codexHome || process.env.CODEX_HOME),
    error: scope.error,
  };
}

async function usableRoot(root: string): Promise<boolean> {
  try {
    const stat = await fs.stat(root);
    if (!stat.isDirectory()) return false;
    for (const name of ["sessions", "archived_sessions"]) {
      try {
        const dir = await fs.lstat(join(root, name));
        if (dir.isDirectory() && !dir.isSymbolicLink()) return true;
      } catch {
        // Try the next fixed directory.
      }
    }
  } catch {
    // A missing or unreadable root is not usable.
  }
  return false;
}

export async function resolveCodexHomeFromValues(
  values: WorkspaceSettingsValues & { codexHome?: string },
  options: { home?: string; env?: string | null } = {},
): Promise<{ root: string | null; error: string | null }> {
  const home = resolve(options.home ?? homedir());
  let homeReal = home;
  try {
    homeReal = realpathSync(home);
  } catch {
    // A missing home can still be compared lexically.
  }

  // An explicit plugin setting is the user's override. It must stay inside the
  // daemon user's home and never silently fall through to another root.
  if (values.codexHome) {
    if (!isAbsolute(values.codexHome)) {
      return { root: null, error: "手动配置的 Codex home 必须是绝对路径" };
    }
    let root: string;
    try {
      root = realpathSync(resolve(values.codexHome));
    } catch {
      return { root: null, error: "手动配置的 Codex home 不存在或不可读" };
    }
    const rel = relative(homeReal, root);
    if (rel === ".." || rel.startsWith(".." + sep) || isAbsolute(rel)) {
      return { root: null, error: "手动配置的 Codex home 必须位于 daemon 用户家目录内" };
    }
    if (!await usableRoot(root)) {
      return { root: null, error: "手动配置的 Codex home 下没有可用的 sessions/ 或 archived_sessions/ 目录" };
    }
    return { root, error: null };
  }

  // CODEX_HOME is the daemon administrator's external root. Normalize it, then
  // require its resolved path to stay under the configured root's parent.
  const rawEnv = options.env === undefined ? process.env.CODEX_HOME : options.env;
  const env = rawEnv?.trim();
  if (env && isAbsolute(env)) {
    const normalized = resolve(env);
    const parent = dirname(normalized);
    const rel = relative(parent, normalized);
    if (rel !== ".." && !rel.startsWith(".." + sep) && !isAbsolute(rel)) {
      let root: string | null = null;
      try {
        root = realpathSync(normalized);
      } catch {
        // Try the configured fallbacks.
      }
      if (root !== null) {
        const rootRel = relative(parent, root);
        if (rootRel !== ".." && !rootRel.startsWith(".." + sep) && !isAbsolute(rootRel) && await usableRoot(root)) {
          return { root, error: null };
        }
      }
    }
  }

  // With no explicit setting, keep the daemon user's default Codex home.
  const candidate = join(home, ".codex");
  {
    const normalized = resolve(candidate);
    let root: string;
    try {
      root = realpathSync(normalized);
    } catch {
      return { root: null, error: "未找到 Codex 会话目录；请设置 CODEX_HOME 或插件 codexHome" };
    }
    const rel = relative(homeReal, root);
    if (rel === ".." || rel.startsWith(".." + sep) || isAbsolute(rel)) {
      return { root: null, error: "默认 Codex home 不在 daemon 用户家目录内" };
    }
    if (await usableRoot(root)) return { root, error: null };
  }
  return { root: null, error: "未找到 Codex 会话目录；请设置 CODEX_HOME 或插件 codexHome" };
}

export async function resolveCodexHome(
  settings?: CodexHomeSettings,
  options: { home?: string; env?: string | null } = {},
): Promise<{ root: string | null; error: string | null }> {
  const { values } = await readSettingsSnapshot(settings);
  return resolveCodexHomeFromValues(values, options);
}

function empty(
  workspaceId: string,
  eligible: number,
  unavailable: number,
  error: string,
): RpcOutput<typeof cumulativeUsageRpc> {
  return {
    workspaceId,
    inputTokens: 0,
    cachedInputTokens: 0,
    covered: 0,
    eligible,
    missing: eligible,
    unavailable,
    rate: null,
    error,
    latestSamples: [],
    recentTurn: null,
    turns: {
      sessions: 0,
      completed: 0,
      speedSamples: 0,
      firstTokenSamples: 0,
      outputTokens: 0,
      elapsedMs: 0,
      firstTokenTotalMs: 0,
    },
  };
}

interface RequestOptions {
  settings?: CodexHomeSettings;
  codexHome?: string;
  /** Tests only: a fixed Claude home, like codexHome. */
  claudeHome?: string;
  cumulativeEnabled?: boolean;
  workspaceIds?: string[];
  allWorkspaces?: boolean;
}

interface RequestContext {
  scope: ReturnType<typeof effectiveWorkspaceScope>;
  revision: string | null;
  values: HomeValues;
}

/**
 * One settings snapshot decides both the scope and the data root. Tests may
 * pass explicit options, which carry no store revision.
 */
async function requestContext(options: RequestOptions): Promise<RequestContext> {
  const explicit = options.cumulativeEnabled !== undefined ||
    options.workspaceIds !== undefined ||
    options.allWorkspaces !== undefined;
  const snapshot = explicit
    ? {
      values: {
        cumulativeEnabled: options.cumulativeEnabled,
        workspaceIds: options.workspaceIds,
        allWorkspaces: options.allWorkspaces,
      } as HomeValues,
      revision: null,
    }
    : await readSettingsSnapshot(options.settings);
  return {
    scope: effectiveWorkspaceScope(snapshot.values),
    revision: snapshot.revision,
    values: snapshot.values,
  };
}

/** Directory probing happens only after scope and exact-agent checks pass. */
async function resolveRoot(
  options: RequestOptions,
  context: RequestContext,
): Promise<{ root: string | null; error: string | null }> {
  return options.codexHome
    ? { root: options.codexHome, error: null }
    : resolveCodexHomeFromValues(context.values);
}

async function resolveClaudeRoot(
  options: RequestOptions,
  context: RequestContext,
): Promise<{ root: string | null; error: string | null }> {
  return options.claudeHome
    ? { root: options.claudeHome, error: null }
    : resolveClaudeHomeFromValues(context.values);
}

/** The session kind behind an agent; custom providers keep the adapter marker. */
function sessionKind(agent: { provider?: unknown; persistence?: { metadata?: { provider?: unknown } | null } | null }): "codex" | "claude" | null {
  return sessionKindOf(agent.provider, agent.persistence?.metadata?.provider);
}

const STALE = "设置已变化，已丢弃本次读取";

async function collectCumulativeUsageUncached(
  input: RpcInput<typeof cumulativeUsageRpc>,
  paseo: PluginHandlerContext["paseo"],
  options: RequestOptions,
  context: RequestContext,
  refresh: boolean,
): Promise<RpcOutput<typeof cumulativeUsageRpc>> {
  const workspaceId = input.workspaceId;
  const { scope } = context;
  if (!scope.enabled) {
    return empty(workspaceId, 0, 0, "累计统计未启用");
  }
  if (scope.error) {
    return empty(workspaceId, 0, 0, scope.error);
  }
  if (!scope.allWorkspaces && !scope.workspaceIds.includes(workspaceId)) {
    return empty(workspaceId, 0, 0, "当前 workspace 不在本机累计用量允许范围");
  }

  const agentIds = [...new Set(input.agentIds)];
  const eligible = new Map<string, number | null>();
  const claudeEligible = new Map<string, string | null>();
  /** The requesting agent that first named each Claude session; one sample per conversation. */
  const claudeAgent = new Map<string, string>();
  let unavailable = 0;

  for (const agentId of agentIds) {
    let result;
    try {
      result = await paseo.agents.ref(agentId).refresh();
    } catch {
      unavailable += 1;
      continue;
    }
    const agent = result?.agent;
    if (!agent || agent.workspaceId !== workspaceId || agent.archivedAt || agent.background) {
      unavailable += 1;
      continue;
    }
    const kind = sessionKind(agent);
    if (kind === null) {
      unavailable += 1;
      continue;
    }
    const nativeHandle = agent.persistence?.nativeHandle;
    if (typeof nativeHandle !== "string" || !UUID_RE.test(nativeHandle)) {
      unavailable += 1;
      continue;
    }
    if (kind === "claude") {
      const cwd = (agent as { cwd?: unknown }).cwd;
      const uuid = nativeHandle.toLowerCase();
      if (!claudeEligible.has(uuid) || claudeEligible.get(uuid) === null) {
        claudeEligible.set(uuid, typeof cwd === "string" && isAbsolute(cwd) ? cwd : null);
      }
      if (!claudeAgent.has(uuid)) claudeAgent.set(uuid, agentId);
      continue;
    }
    const created = typeof agent.createdAt === "string" ? Date.parse(agent.createdAt) : NaN;
    const createdMs = Number.isFinite(created) ? created : null;
    const uuid = nativeHandle.toLowerCase();
    const previous = eligible.get(uuid);
    if (previous === undefined) eligible.set(uuid, createdMs);
    else if (createdMs !== null && (previous === null || createdMs < previous)) eligible.set(uuid, createdMs);
  }

  const total = eligible.size + claudeEligible.size;
  if (total === 0) {
    return empty(workspaceId, 0, unavailable, "当前工作区没有可确认的 Codex 或 Claude 会话");
  }

  // Settings may have changed while agent.refresh() was in flight. Stop before
  // resolving any root; the request keeps its original grant only.
  if (await settingsChangedSince(options.settings, context.revision)) {
    return empty(workspaceId, total, unavailable, STALE);
  }

  // Each data root is probed only when this request has sessions of that kind.
  // One kind's missing root leaves its sessions missing without hiding the other.
  const codexRoot = eligible.size > 0 ? await resolveRoot(options, context) : { root: null, error: null };
  const claudeRoot = claudeEligible.size > 0 ? await resolveClaudeRoot(options, context) : { root: null, error: null };
  if (!codexRoot.root && !claudeRoot.root) {
    const errors = [codexRoot.error, claudeRoot.error].filter((error): error is string => Boolean(error));
    return empty(workspaceId, total, unavailable, errors.join("；") || "未找到会话目录");
  }
  if (await settingsChangedSince(options.settings, context.revision)) {
    return empty(workspaceId, total, unavailable, STALE);
  }

  const key = `${workspaceId}|${[...new Set(input.agentIds)].sort().join(",")}|${[...eligible.keys()].sort().join(",")}|${[...claudeEligible.keys()].sort().join(",")}|${unavailable}|${codexRoot.root ?? ""}|${claudeRoot.root ?? ""}|${context.revision ?? ""}|${scope.allWorkspaces ? "*" : scope.workspaceIds.join(",")}`;
  if (!refresh) {
    const cached = workspaceCache.get(key);
    if (cached && Date.now() - cached.at < WORKSPACE_TTL_MS) return cached.value;
    const running = workspaceInflight.get(key);
    if (running) return running;
  }

  let realRoot: string | null = null;
  let realClaudeRoot: string | null = null;
  try {
    if (codexRoot.root) realRoot = await fs.realpath(codexRoot.root);
  } catch {
    realRoot = null;
  }
  try {
    if (claudeRoot.root) realClaudeRoot = await fs.realpath(claudeRoot.root);
  } catch {
    realClaudeRoot = null;
  }
  if (realRoot === null && realClaudeRoot === null) {
    return empty(workspaceId, total, unavailable, "会话目录不可读");
  }

  const generation = cacheGeneration;
  let task!: Promise<RpcOutput<typeof cumulativeUsageRpc>>;
  task = (async () => {
    const reads = realRoot === null ? [] : await Promise.all([...eligible].map(async ([uuid, createdMs]) => {
      const file = await findSessionFile(realRoot!, uuid, createdMs, refresh);
      if (!file) return null;
      return readSessionCounts(file);
    }));
    const claudeReads = realClaudeRoot === null ? [] : await Promise.all([...claudeEligible].map(async ([uuid, cwd]) => {
      const file = await findClaudeTranscript(realClaudeRoot!, uuid, cwd, refresh);
      if (!file) return null;
      const read = await readClaudeCounts(file);
      return read ? { agentId: claudeAgent.get(uuid)!, read } : null;
    }));
    if (await settingsChangedSince(options.settings, context.revision)) {
      return empty(workspaceId, total, unavailable, STALE);
    }
    const samples = [...reads.map((read) => read?.sample ?? null), ...claudeReads.map((entry) => entry?.read.sample ?? null)]
      .filter((sample): sample is CacheCounts => sample !== null);
    const latestSamples = claudeReads.flatMap((entry) =>
      entry?.read.latest ? [{ agentId: entry.agentId, input: entry.read.latest.input, cached: entry.read.latest.cached }] : []);
    const totals = summarizeLatestSamples(samples);
    // One successful turn per rollout is already folded into constant-space
    // sums while reading; newest wins by completion time, never by speed.
    let turns = emptyTurnTotals();
    let recentTurn: CompletedTurn | null = null;
    let turnSessions = 0;
    for (const read of [...reads, ...claudeReads.map((entry) => entry?.read ?? null)]) {
      if (!read) continue;
      turns = mergeTurnTotals(turns, read.turns);
      if (read.turns.completed > 0) turnSessions += 1;
      if (read.lastSuccessful) recentTurn = latestCompletedTurn(recentTurn, read.lastSuccessful);
    }
    return {
      workspaceId,
      inputTokens: totals.input,
      cachedInputTokens: totals.cached,
      covered: totals.covered,
      eligible: total,
      missing: total - totals.covered,
      unavailable,
      rate: totals.rate,
      error: null,
      latestSamples,
      recentTurn: recentTurn === null ? null : {
        completedAt: recentTurn.completedAt,
        outputTokens: recentTurn.outputTokens,
        elapsedMs: recentTurn.elapsedMs,
        firstTokenMs: recentTurn.firstTokenMs,
      },
      turns: {
        sessions: turnSessions,
        completed: turns.completed,
        speedSamples: turns.speedSamples,
        firstTokenSamples: turns.firstTokenSamples,
        outputTokens: turns.outputTokens,
        elapsedMs: turns.elapsedMs,
        firstTokenTotalMs: turns.firstTokenTotalMs,
      },
    };
  })().then((value) => {
    if (!refresh && generation === cacheGeneration) {
      workspaceCache.set(key, { at: Date.now(), value });
    }
    return value;
  }).finally(() => {
    if (workspaceInflight.get(key) === task) workspaceInflight.delete(key);
  });
  if (!refresh) workspaceInflight.set(key, task);
  return task;
}

function emptyTurn(
  reason: "not-codex" | "scope" | "missing-samples" | "read-failed",
  source: "codex" | "claude" | null = null,
): RpcOutput<typeof turnOutputRpc> {
  return { outputTokens: null, elapsedMs: null, firstTokenMs: null, reason, source };
}

/**
 * The latest completed Codex turn for one agent. It shares the cumulative
 * feature's settings snapshot, gates, and rollout reader; timing and first-token
 * values do not depend on a cache sample.
 */
export async function collectTurnOutput(
  input: RpcInput<typeof turnOutputRpc>,
  paseo: PluginHandlerContext["paseo"],
  options: RequestOptions = {},
): Promise<RpcOutput<typeof turnOutputRpc>> {
  const context = await requestContext(options);
  const { scope } = context;
  if (!scope.enabled || scope.error) return emptyTurn("scope");
  if (!scope.allWorkspaces && !scope.workspaceIds.includes(input.workspaceId)) return emptyTurn("scope");

  let result;
  try {
    result = await paseo.agents.ref(input.agentId).refresh();
  } catch {
    return emptyTurn("read-failed");
  }
  const agent = result?.agent;
  if (!agent || agent.workspaceId !== input.workspaceId || agent.archivedAt || agent.background) {
    return emptyTurn("read-failed");
  }
  const kind = sessionKind(agent);
  if (kind === null) return emptyTurn("not-codex");
  const nativeHandle = agent.persistence?.nativeHandle;
  if (typeof nativeHandle !== "string" || !UUID_RE.test(nativeHandle)) return emptyTurn("not-codex", kind);
  if (kind === "claude") return collectClaudeTurn(agent, nativeHandle.toLowerCase(), options, context);

  if (await settingsChangedSince(options.settings, context.revision)) return emptyTurn("scope", "codex");
  const root = await resolveRoot(options, context);
  if (!root.root) return emptyTurn("read-failed", "codex");
  if (await settingsChangedSince(options.settings, context.revision)) return emptyTurn("scope", "codex");

  let realRoot: string;
  try {
    realRoot = await fs.realpath(root.root);
  } catch {
    return emptyTurn("read-failed", "codex");
  }

  const created = typeof agent.createdAt === "string" ? Date.parse(agent.createdAt) : NaN;
  const createdMs = Number.isFinite(created) ? created : null;
  // A newly written rollout must not sit behind a 30 second negative path cache.
  const file = await findSessionFile(realRoot, nativeHandle.toLowerCase(), createdMs, true);
  if (!file) return emptyTurn("missing-samples", "codex");
  const read = await readSessionCounts(file);
  if (!read?.lastTurn) return emptyTurn("missing-samples", "codex");

  if (await settingsChangedSince(options.settings, context.revision)) return emptyTurn("scope", "codex");

  const { outputTokens, elapsedMs, firstTokenMs } = read.lastTurn;
  // Independent first-token timing survives a zero or absent elapsed duration.
  if (elapsedMs === null && firstTokenMs === null && outputTokens === null) return emptyTurn("missing-samples", "codex");
  return {
    outputTokens,
    elapsedMs,
    firstTokenMs,
    reason: outputTokens === null ? "missing-samples" : null,
    source: "codex",
  };
}

/** The latest completed Claude turn, from the session's own transcript. */
async function collectClaudeTurn(
  agent: { cwd?: unknown },
  uuid: string,
  options: RequestOptions,
  context: RequestContext,
): Promise<RpcOutput<typeof turnOutputRpc>> {
  if (await settingsChangedSince(options.settings, context.revision)) return emptyTurn("scope", "claude");
  const root = await resolveClaudeRoot(options, context);
  if (!root.root) return emptyTurn("read-failed", "claude");
  if (await settingsChangedSince(options.settings, context.revision)) return emptyTurn("scope", "claude");
  let realRoot: string;
  try {
    realRoot = await fs.realpath(root.root);
  } catch {
    return emptyTurn("read-failed", "claude");
  }
  const cwd = typeof agent.cwd === "string" && isAbsolute(agent.cwd) ? agent.cwd : null;
  const file = await findClaudeTranscript(realRoot, uuid, cwd, true);
  if (!file) return emptyTurn("missing-samples", "claude");
  const read = await readClaudeCounts(file);
  if (!read?.lastTurn) return emptyTurn("missing-samples", "claude");
  if (await settingsChangedSince(options.settings, context.revision)) return emptyTurn("scope", "claude");
  const { outputTokens, elapsedMs, firstTokenMs } = read.lastTurn;
  if (elapsedMs === null && outputTokens === null) return emptyTurn("missing-samples", "claude");
  return {
    outputTokens,
    elapsedMs,
    firstTokenMs,
    reason: outputTokens === null ? "missing-samples" : null,
    source: "claude",
  };
}

export function createTurnOutputHandler(settings?: CodexHomeSettings) {
  return (input: RpcInput<typeof turnOutputRpc>, context: PluginHandlerContext) =>
    collectTurnOutput(input, context.paseo, { settings });
}

export function createCumulativeHandler(settings?: CodexHomeSettings) {
  return (input: RpcInput<typeof cumulativeUsageRpc>, context: PluginHandlerContext) =>
    collectCumulativeUsage(input, context.paseo, { settings });
}

export async function collectCumulativeUsage(
  input: RpcInput<typeof cumulativeUsageRpc>,
  paseo: PluginHandlerContext["paseo"],
  options: RequestOptions = {},
): Promise<RpcOutput<typeof cumulativeUsageRpc>> {
  const context = await requestContext(options);
  const { scope } = context;
  if (!scope.enabled) return empty(input.workspaceId, 0, 0, "累计统计未启用");
  if (scope.error) return empty(input.workspaceId, 0, 0, scope.error);
  return collectCumulativeUsageUncached(input, paseo, options, context, input.refresh === true);
}

type ScopeSettings = CodexHomeSettings & {
  subscribe(listener: () => void | Promise<void>): () => void;
};

/** Keeps the settings stream open until the client releases it, then unsubscribes. */
export function createScopeSubscriptionHandler(settings?: ScopeSettings) {
  return async (
    _input: unknown,
    context: {
      push(event: Awaited<ReturnType<typeof workspaceScope>>): Promise<void>;
      signal: AbortSignal;
    },
  ) => {
    let unsubscribe: (() => void) | null = null;
    let closed = false;
    const stop = () => {
      closed = true;
      unsubscribe?.();
      unsubscribe = null;
    };
    context.signal.addEventListener("abort", stop, { once: true });
    try {
      if (closed) return;
      if (settings) {
        unsubscribe = settings.subscribe(async () => {
          if (closed) return;
          clearCumulativeCaches();
          await context.push(await workspaceScope(settings));
        });
      }
      if (closed) return;
      await context.push(await workspaceScope(settings));
      if (closed) return;
      await new Promise<void>((resolve) => {
        if (context.signal.aborted) resolve();
        else context.signal.addEventListener("abort", () => resolve(), { once: true });
      });
    } finally {
      context.signal.removeEventListener("abort", stop);
      stop();
    }
  };
}
