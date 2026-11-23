import { constants, promises as fs, realpathSync } from "node:fs";
import type { FileHandle } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, isAbsolute, join, relative, resolve, sep } from "node:path";
import type { RpcInput, RpcOutput } from "@getpaseo/plugin";
import type { PluginHandlerContext } from "@getpaseo/plugin/server";
import type { cumulativeUsageRpc, turnOutputRpc } from "../shared/cumulative.ts";
import { summarizeLatestSamples } from "../shared/metrics.ts";
import { effectiveWorkspaceScope, type WorkspaceSettingsValues } from "../shared/scope.ts";

export interface CodexHomeSettings {
  read(): Promise<
    | { status: "ready"; revision?: string; values: WorkspaceSettingsValues & { codexHome?: string } }
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
  lastTurn: CompletedTurn | null;
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
}

function emptyProjection(): ProjectedEvent {
  return {
    eventType: null, payloadType: null, timestamp: null, turnId: null,
    firstTokenMs: null, errorPresent: false, input: null, cached: null, output: null,
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
  const match = /^-?\d+(?:\.\d+)?/.exec(raw.slice(index, index + 32));
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
    if (raw[index] === "}") break;
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
  if (event.eventType !== "event_msg") return;
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
      state.lastTurn = { outputTokens: null, elapsedMs: null, firstTokenMs: null };
      return;
    }
    const finalTrusted = !open.broken && open.finalOutput !== null &&
      open.finalAt !== null && open.finalAt >= open.startedAt && open.finalAt <= at;
    const outputValid = finalTrusted && open.baseline !== null && open.finalOutput! >= open.baseline;
    state.trustedOutput = finalTrusted ? open.finalOutput : null;
    state.lastTurn = {
      outputTokens: outputValid ? open.finalOutput! - open.baseline! : null,
      elapsedMs: at >= open.startedAt ? at - open.startedAt : null,
      firstTokenMs,
    };
    return;
  }

  if (type === "turn_aborted" || type === "thread_rolled_back") {
    state.openTurn = null;
    state.lastTurn = null;
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
  if (open) {
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
      return state.valid ? countsOf(state) : null;
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
    return state.valid ? countsOf(state) : null;
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

interface SettingsSnapshot {
  values: WorkspaceSettingsValues & { codexHome?: string };
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
  };
}

interface RequestOptions {
  settings?: CodexHomeSettings;
  codexHome?: string;
  cumulativeEnabled?: boolean;
  workspaceIds?: string[];
  allWorkspaces?: boolean;
}

interface RequestContext {
  scope: ReturnType<typeof effectiveWorkspaceScope>;
  revision: string | null;
  values: WorkspaceSettingsValues & { codexHome?: string };
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
      } as WorkspaceSettingsValues & { codexHome?: string },
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
    const marker = agent.persistence?.metadata?.provider;
    if (agent.provider !== "codex" && marker !== "codex") {
      unavailable += 1;
      continue;
    }
    const nativeHandle = agent.persistence?.nativeHandle;
    if (typeof nativeHandle !== "string" || !UUID_RE.test(nativeHandle)) {
      unavailable += 1;
      continue;
    }
    const created = typeof agent.createdAt === "string" ? Date.parse(agent.createdAt) : NaN;
    const createdMs = Number.isFinite(created) ? created : null;
    const uuid = nativeHandle.toLowerCase();
    const previous = eligible.get(uuid);
    if (previous === undefined) eligible.set(uuid, createdMs);
    else if (createdMs !== null && (previous === null || createdMs < previous)) eligible.set(uuid, createdMs);
  }

  if (eligible.size === 0) {
    return empty(workspaceId, 0, unavailable, "当前工作区没有可确认的 Codex 会话");
  }

  // Settings may have changed while agent.refresh() was in flight. Stop before
  // resolving any root; the request keeps its original grant only.
  if (await settingsChangedSince(options.settings, context.revision)) {
    return empty(workspaceId, eligible.size, unavailable, STALE);
  }

  const root = await resolveRoot(options, context);
  if (!root.root) {
    return empty(workspaceId, eligible.size, unavailable, root.error ?? "未找到 Codex 会话目录");
  }
  if (await settingsChangedSince(options.settings, context.revision)) {
    return empty(workspaceId, eligible.size, unavailable, STALE);
  }

  const key = `${workspaceId}|${[...eligible.keys()].sort().join(",")}|${root.root}|${context.revision ?? ""}|${scope.allWorkspaces ? "*" : scope.workspaceIds.join(",")}`;
  if (!refresh) {
    const cached = workspaceCache.get(key);
    if (cached && Date.now() - cached.at < WORKSPACE_TTL_MS) return cached.value;
    const running = workspaceInflight.get(key);
    if (running) return running;
  }

  let realRoot: string;
  try {
    realRoot = await fs.realpath(root.root);
  } catch {
    return empty(workspaceId, eligible.size, unavailable, "Codex 会话目录不可读");
  }

  const generation = cacheGeneration;
  let task!: Promise<RpcOutput<typeof cumulativeUsageRpc>>;
  task = (async () => {
    const reads = await Promise.all([...eligible].map(async ([uuid, createdMs]) => {
      const file = await findSessionFile(realRoot, uuid, createdMs, refresh);
      if (!file) return null;
      return readSessionCounts(file);
    }));
    if (await settingsChangedSince(options.settings, context.revision)) {
      return empty(workspaceId, eligible.size, unavailable, STALE);
    }
    const samples = reads
      .map((read) => read?.sample ?? null)
      .filter((sample): sample is CacheCounts => sample !== null);
    const totals = summarizeLatestSamples(samples);
    return {
      workspaceId,
      inputTokens: totals.input,
      cachedInputTokens: totals.cached,
      covered: totals.covered,
      eligible: eligible.size,
      missing: eligible.size - totals.covered,
      unavailable,
      rate: totals.rate,
      error: null,
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

function emptyTurn(reason: "not-codex" | "scope" | "missing-samples" | "read-failed"): RpcOutput<typeof turnOutputRpc> {
  return { outputTokens: null, elapsedMs: null, firstTokenMs: null, reason };
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
  const marker = agent.persistence?.metadata?.provider;
  if (agent.provider !== "codex" && marker !== "codex") return emptyTurn("not-codex");
  const nativeHandle = agent.persistence?.nativeHandle;
  if (typeof nativeHandle !== "string" || !UUID_RE.test(nativeHandle)) return emptyTurn("not-codex");

  if (await settingsChangedSince(options.settings, context.revision)) return emptyTurn("scope");
  const root = await resolveRoot(options, context);
  if (!root.root) return emptyTurn("read-failed");
  if (await settingsChangedSince(options.settings, context.revision)) return emptyTurn("scope");

  let realRoot: string;
  try {
    realRoot = await fs.realpath(root.root);
  } catch {
    return emptyTurn("read-failed");
  }

  const created = typeof agent.createdAt === "string" ? Date.parse(agent.createdAt) : NaN;
  const createdMs = Number.isFinite(created) ? created : null;
  // A newly written rollout must not sit behind a 30 second negative path cache.
  const file = await findSessionFile(realRoot, nativeHandle.toLowerCase(), createdMs, true);
  if (!file) return emptyTurn("missing-samples");
  const read = await readSessionCounts(file);
  if (!read?.lastTurn) return emptyTurn("missing-samples");

  if (await settingsChangedSince(options.settings, context.revision)) return emptyTurn("scope");

  const { outputTokens, elapsedMs, firstTokenMs } = read.lastTurn;
  // Independent first-token timing survives a zero or absent elapsed duration.
  if (elapsedMs === null && firstTokenMs === null && outputTokens === null) return emptyTurn("missing-samples");
  return {
    outputTokens,
    elapsedMs,
    firstTokenMs,
    reason: outputTokens === null ? "missing-samples" : null,
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
