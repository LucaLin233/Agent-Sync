import { constants, promises as fs } from "node:fs";
import type { FileHandle } from "node:fs/promises";
import { homedir } from "node:os";
import { isAbsolute, join, sep } from "node:path";
import type { RpcInput, RpcOutput } from "@getpaseo/plugin";
import type { PluginHandlerContext } from "@getpaseo/plugin/server";
import type { cumulativeUsageRpc } from "../shared/cumulative.ts";
import { summarizeLatestSamples } from "../shared/metrics.ts";

export interface CodexHomeSettings {
  read(): Promise<
    | { status: "ready"; values: { codexHome?: string; workspaceIds?: string[] } }
    | { status: "invalid"; error: string }
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

interface SessionCounts {
  input: number;
  cached: number;
}

interface FileState extends SessionCounts {
  dev: number;
  ino: number;
  size: number;
  mtimeMs: number;
  ctimeMs: number;
  offset: number;
  valid: boolean;
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
const inflight = new Map<string, Promise<SessionCounts | null>>();
const workspaceCache = new Map<string, { at: number; value: RpcOutput<typeof cumulativeUsageRpc> }>();
const workspaceInflight = new Map<string, Promise<RpcOutput<typeof cumulativeUsageRpc>>>();

export function clearCumulativeCaches() {
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

function isWorkspaceId(value: unknown): value is string {
  return typeof value === "string" && value.length > 0 && value.length <= 128;
}

function parseTokenLine(line: string, state: FileState) {
  const head = line.slice(0, 240);
  if (!head.includes("event_msg") || !head.includes("token_count")) return;
  let parsed: unknown;
  try {
    parsed = JSON.parse(line);
  } catch {
    return;
  }
  const record = asRecord(parsed);
  if (!record || record.type !== "event_msg") return;
  const payload = asRecord(record.payload);
  if (!payload || payload.type !== "token_count") return;
  const info = asRecord(payload.info);
  const total = asRecord(info?.total_token_usage);
  if (!total) return;
  const input = total.input_tokens;
  const cached = total.cached_input_tokens;
  if (!isToken(input) || !isToken(cached) || cached > input) return;
  state.input = input;
  state.cached = cached;
  state.valid = true;
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
    valid: false,
  };
}

function sameFile(a: { dev: number; ino: number }, b: { dev: number; ino: number }) {
  return a.dev === b.dev && a.ino === b.ino;
}

function sameState(a: FileState, b: { dev: number; ino: number; size: number; mtimeMs: number; ctimeMs: number }) {
  return a.dev === b.dev && a.ino === b.ino && a.size === b.size &&
    a.mtimeMs === b.mtimeMs && a.ctimeMs === b.ctimeMs;
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
      parseTokenLine(pending.subarray(0, newline).toString("utf8"), state);
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

async function readSessionCountsUncached(file: SessionFile): Promise<SessionCounts | null> {
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
      return state.valid ? { input: state.input, cached: state.cached } : null;
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
    return state.valid ? { input: state.input, cached: state.cached } : null;
  } catch {
    forget(file.path);
    return null;
  } finally {
    if (handle) await handle.close().catch(() => undefined);
  }
}

function readSessionCounts(file: SessionFile): Promise<SessionCounts | null> {
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

async function findSessionFile(root: string, uuid: string, createdMs: number | null): Promise<SessionFile | null> {
  const key = `${root}|${uuid}|${createdMs ?? ""}`;
  const cached = pathCache.get(key);
  if (cached && Date.now() - cached.at < PATH_TTL_MS) return cached.file;

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
      pathCache.set(key, { at: Date.now(), file: null });
      return null;
    }
  }
  pathCache.set(key, { at: Date.now(), file: best });
  return best;
}

async function readSettings(settings?: CodexHomeSettings): Promise<{ codexHome?: string; workspaceIds?: string[] }> {
  if (!settings) return {};
  try {
    const state = await settings.read();
    if (state.status === "ready") return state.values;
  } catch {
    // An unreadable setting means no scope; never widen the default.
  }
  return {};
}

export async function workspaceScope(settings?: CodexHomeSettings) {
  const values = await readSettings(settings);
  const workspaceIds = (values.workspaceIds ?? []).filter(isWorkspaceId);
  return {
    workspaceIds,
    codexHomeConfigured: Boolean(values.codexHome || process.env.CODEX_HOME),
    error: workspaceIds.length > 0 ? null : "未配置 workspace 允许列表",
  };
}

export async function resolveCodexHome(settings?: CodexHomeSettings): Promise<{ root: string | null; error: string | null }> {
  const values = await readSettings(settings);
  const candidates: string[] = [];
  const env = process.env.CODEX_HOME?.trim();
  if (env) candidates.push(env);
  if (values.codexHome) candidates.push(values.codexHome);
  candidates.push(join(homedir(), ".codex"));

  for (const candidate of candidates) {
    if (!isAbsolute(candidate)) continue;
    try {
      const root = await fs.realpath(candidate);
      const stat = await fs.stat(root);
      if (!stat.isDirectory()) continue;
      for (const name of ["sessions", "archived_sessions"]) {
        try {
          const dir = await fs.lstat(join(root, name));
          if (dir.isDirectory() && !dir.isSymbolicLink()) return { root, error: null };
        } catch {
          // Try the next fixed root.
        }
      }
    } catch {
      // Try the next candidate.
    }
  }
  return { root: null, error: "未找到 Codex 会话目录；请设置 CODEX_HOME 或插件 codexHome" };
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

async function collectCumulativeUsageUncached(
  input: RpcInput<typeof cumulativeUsageRpc>,
  paseo: PluginHandlerContext["paseo"],
  options: { settings?: CodexHomeSettings; codexHome?: string; workspaceIds?: string[] } = {},
): Promise<RpcOutput<typeof cumulativeUsageRpc>> {
  const workspaceId = input.workspaceId;
  const configured = options.workspaceIds
    ? options.workspaceIds.filter(isWorkspaceId)
    : (await readSettings(options.settings)).workspaceIds?.filter(isWorkspaceId) ?? [];
  if (configured.length === 0) {
    return empty(workspaceId, 0, 0, "未配置 workspace 允许列表");
  }
  if (!configured.includes(workspaceId)) {
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
    if (!agent || agent.workspaceId !== workspaceId || agent.archivedAt) {
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

  const root = options.codexHome
    ? { root: options.codexHome, error: null }
    : await resolveCodexHome(options.settings);
  if (!root.root) {
    return empty(workspaceId, eligible.size, unavailable, root.error ?? "未找到 Codex 会话目录");
  }

  let realRoot = root.root;
  try {
    realRoot = await fs.realpath(root.root);
  } catch {
    return empty(workspaceId, eligible.size, unavailable, "Codex 会话目录不可读");
  }

  const counts = await Promise.all([...eligible].map(async ([uuid, createdMs]) => {
    const file = await findSessionFile(realRoot, uuid, createdMs);
    if (!file) return null;
    return readSessionCounts(file);
  }));

  const samples = counts.filter((sample): sample is SessionCounts => sample !== null);
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
}

export function createCumulativeHandler(settings?: CodexHomeSettings) {
  return (input: RpcInput<typeof cumulativeUsageRpc>, context: PluginHandlerContext) =>
    collectCumulativeUsage(input, context.paseo, { settings });
}

export function collectCumulativeUsage(
  input: RpcInput<typeof cumulativeUsageRpc>,
  paseo: PluginHandlerContext["paseo"],
  options: { settings?: CodexHomeSettings; codexHome?: string; workspaceIds?: string[] } = {},
): Promise<RpcOutput<typeof cumulativeUsageRpc>> {
  const key = `${input.workspaceId}|${[...new Set(input.agentIds)].sort().join(",")}|${options.codexHome ?? ""}|${options.workspaceIds?.join(",") ?? ""}`;
  const cached = workspaceCache.get(key);
  if (cached && Date.now() - cached.at < WORKSPACE_TTL_MS) return Promise.resolve(cached.value);
  const running = workspaceInflight.get(key);
  if (running) return running;
  const task = collectCumulativeUsageUncached(input, paseo, options)
    .then((value) => {
      workspaceCache.set(key, { at: Date.now(), value });
      return value;
    })
    .finally(() => workspaceInflight.delete(key));
  workspaceInflight.set(key, task);
  return task;
}
