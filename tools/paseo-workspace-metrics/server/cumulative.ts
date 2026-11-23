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
    | { status: "ready"; values: WorkspaceSettingsValues & { codexHome?: string } }
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

export interface CompletedTurn {
  /** Cumulative output rose by this much between the turn's native boundaries. */
  outputTokens: number | null;
  /** Both boundaries come from the same rollout, never from client events. */
  elapsedMs: number | null;
  /** Codex's own time_to_first_token_ms for that completed turn, if reported. */
  firstTokenMs: number | null;
}

interface SessionCounts {
  input: number;
  cached: number;
  output: number;
  lastTurn: CompletedTurn | null;
}

interface FileState extends SessionCounts {
  dev: number;
  ino: number;
  size: number;
  mtimeMs: number;
  ctimeMs: number;
  offset: number;
  valid: boolean;
  outputSeen: boolean;
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
const inflight = new Map<string, Promise<SessionCounts | null>>();
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

function parseLine(line: string, state: FileState) {
  const head = line.slice(0, 240);
  if (!head.includes("event_msg")) return;
  if (
    !head.includes("token_count") &&
    !head.includes("task_started") &&
    !head.includes("task_complete") &&
    !head.includes("turn_aborted") &&
    !head.includes("thread_rolled_back")
  ) return;
  let parsed: unknown;
  try {
    parsed = JSON.parse(line);
  } catch {
    return;
  }
  const record = asRecord(parsed);
  if (!record || record.type !== "event_msg") return;
  const payload = asRecord(record.payload);
  if (!payload) return;
  const at = typeof record.timestamp === "string" ? Date.parse(record.timestamp) : NaN;

  if (payload.type === "task_started") {
    const id = typeof payload.turn_id === "string" ? payload.turn_id : null;
    if (!id || !Number.isFinite(at)) return;
    // Only a cumulative value actually reported by the rollout can be a
    // baseline. Reading from byte zero does not prove an earlier zero: old,
    // partial, or forked files may lack the marker. An unobserved baseline stays
    // null and never becomes a delta.
    const baseline = state.outputSeen ? state.output : null;
    state.openTurn = { id, startedAt: at, baseline, finalAt: null, finalOutput: null, broken: false };
    return;
  }

  if (payload.type === "task_complete") {
    const id = typeof payload.turn_id === "string" ? payload.turn_id : null;
    const open = state.openTurn;
    if (!id || !open || open.id !== id || !Number.isFinite(at)) return;
    state.openTurn = null;
    // A non-empty error means the turn did not complete successfully. Only the
    // scalar time-to-first-token field is projected; assistant text is ignored.
    const error = payload.error;
    const failed = typeof error === "string"
      ? error.trim().length > 0
      : error !== null && error !== undefined;
    const firstTokenMs = isToken(payload.time_to_first_token_ms) ? payload.time_to_first_token_ms : null;
    if (failed) {
      // A non-empty error is not a successful completion; show nothing for it.
      state.lastTurn = { outputTokens: null, elapsedMs: null, firstTokenMs: null };
      return;
    }
    // Boundary timing and the first-token measurement stand on their own. The
    // output delta additionally needs an observed baseline, an in-turn counter,
    // no regression, and a final count no later than the completion boundary.
    const outputValid = !open.broken && open.baseline !== null &&
      open.finalOutput !== null && open.finalAt !== null &&
      open.finalAt >= open.startedAt && open.finalAt <= at &&
      open.finalOutput >= open.baseline;
    state.lastTurn = {
      outputTokens: outputValid ? open.finalOutput! - open.baseline! : null,
      elapsedMs: at >= open.startedAt ? at - open.startedAt : null,
      firstTokenMs,
    };
    return;
  }

  if (payload.type === "turn_aborted" || payload.type === "thread_rolled_back") {
    // An abort or rollback leaves no completed turn to measure. Drop the open
    // turn and the previous measurement instead of reusing an older snapshot.
    // A rollback also invalidates the observed counter, so the next turn waits
    // for a fresh snapshot before it can form a baseline.
    state.openTurn = null;
    state.lastTurn = null;
    if (payload.type === "thread_rolled_back") state.outputSeen = false;
    return;
  }

  if (payload.type !== "token_count") return;
  const info = asRecord(payload.info);
  const total = asRecord(info?.total_token_usage);
  if (!total) return;
  const input = total.input_tokens;
  const cached = total.cached_input_tokens;
  const output = total.output_tokens;
  if (!isToken(input) || !isToken(cached) || cached > input) {
    // Cache basis stays unchanged; an unusable counter inside an open turn
    // still disqualifies that turn's output delta.
    if (state.openTurn) state.openTurn.broken = true;
    return;
  }
  state.input = input;
  state.cached = cached;
  state.valid = true;
  if (!isToken(output) || !Number.isFinite(at)) {
    if (state.openTurn) state.openTurn.broken = true;
    return;
  }
  // Any in-turn regression disqualifies this turn's delta even if the final
  // value recovers.
  if (state.openTurn && state.outputSeen && output < state.output) state.openTurn.broken = true;
  state.output = output;
  state.outputSeen = true;
  if (state.openTurn) {
    state.openTurn.finalAt = at;
    state.openTurn.finalOutput = output;
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
    output: 0,
    lastTurn: null,
    valid: false,
    outputSeen: false,
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

function countsOf(state: FileState): SessionCounts {
  return {
    input: state.input,
    cached: state.cached,
    output: state.output,
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

async function readSettings(
  settings?: CodexHomeSettings,
): Promise<WorkspaceSettingsValues & { codexHome?: string }> {
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

export async function resolveCodexHome(
  settings?: CodexHomeSettings,
  options: { home?: string; env?: string | null } = {},
): Promise<{ root: string | null; error: string | null }> {
  const values = await readSettings(settings);
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
  options: {
    settings?: CodexHomeSettings;
    codexHome?: string;
    cumulativeEnabled?: boolean;
    workspaceIds?: string[];
    allWorkspaces?: boolean;
    scope?: ReturnType<typeof effectiveWorkspaceScope>;
  } = {},
): Promise<RpcOutput<typeof cumulativeUsageRpc>> {
  const workspaceId = input.workspaceId;
  const scope = options.scope ?? effectiveWorkspaceScope(await resolveWorkspaceValues(options));
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

async function resolveWorkspaceValues(options: {
  settings?: CodexHomeSettings;
  cumulativeEnabled?: boolean;
  workspaceIds?: string[];
  allWorkspaces?: boolean;
}): Promise<WorkspaceSettingsValues> {
  if (
    options.cumulativeEnabled !== undefined ||
    options.workspaceIds !== undefined ||
    options.allWorkspaces !== undefined
  ) {
    return {
      cumulativeEnabled: options.cumulativeEnabled,
      workspaceIds: options.workspaceIds,
      allWorkspaces: options.allWorkspaces,
    };
  }
  return readSettings(options.settings);
}

function emptyTurn(reason: "not-codex" | "scope" | "missing-samples" | "read-failed"): RpcOutput<typeof turnOutputRpc> {
  return { outputTokens: null, elapsedMs: null, firstTokenMs: null, reason };
}

/**
 * Same-turn output for one Codex-backed agent. It reads exactly the rollout the
 * cumulative feature already gates (workspace, archive state, Codex marker, and
 * UUID native handle) and only needs the cumulative output counter plus rollout
 * timestamps. Everything else stays out of the response.
 */
export async function collectTurnOutput(
  input: RpcInput<typeof turnOutputRpc>,
  paseo: PluginHandlerContext["paseo"],
  options: {
    settings?: CodexHomeSettings;
    codexHome?: string;
    cumulativeEnabled?: boolean;
    workspaceIds?: string[];
    allWorkspaces?: boolean;
  } = {},
): Promise<RpcOutput<typeof turnOutputRpc>> {
  const scope = effectiveWorkspaceScope(await resolveWorkspaceValues(options));
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

  const configured = options.codexHome
    ? { root: options.codexHome, error: null }
    : await resolveCodexHome(options.settings);
  if (!configured.root) return emptyTurn("read-failed");
  let root: string;
  try {
    root = await fs.realpath(configured.root);
  } catch {
    return emptyTurn("read-failed");
  }

  const created = typeof agent.createdAt === "string" ? Date.parse(agent.createdAt) : NaN;
  const createdMs = Number.isFinite(created) ? created : null;
  const file = await findSessionFile(root, nativeHandle.toLowerCase(), createdMs);
  if (!file) return emptyTurn("missing-samples");
  const counts = await readSessionCounts(file);
  if (!counts?.lastTurn) return emptyTurn("missing-samples");
  const { outputTokens, elapsedMs, firstTokenMs } = counts.lastTurn;
  if (elapsedMs === null || elapsedMs <= 0) return emptyTurn("missing-samples");
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
  options: {
    settings?: CodexHomeSettings;
    codexHome?: string;
    cumulativeEnabled?: boolean;
    workspaceIds?: string[];
    allWorkspaces?: boolean;
  } = {},
): Promise<RpcOutput<typeof cumulativeUsageRpc>> {
  const scope = effectiveWorkspaceScope(await resolveWorkspaceValues(options));
  if (!scope.enabled) return empty(input.workspaceId, 0, 0, "累计统计未启用");
  if (scope.error) return empty(input.workspaceId, 0, 0, scope.error);
  const key = `${input.workspaceId}|${[...new Set(input.agentIds)].sort().join(",")}|${options.codexHome ?? ""}|${scope.enabled}|${scope.allWorkspaces ? "*" : ""}|${scope.workspaceIds.join(",")}`;
  const cached = workspaceCache.get(key);
  if (cached && Date.now() - cached.at < WORKSPACE_TTL_MS) return Promise.resolve(cached.value);
  const running = workspaceInflight.get(key);
  if (running) return running;
  const generation = cacheGeneration;
  let task: Promise<RpcOutput<typeof cumulativeUsageRpc>>;
  task = collectCumulativeUsageUncached(input, paseo, { ...options, scope })
    .then((value) => {
      if (generation === cacheGeneration) {
        workspaceCache.set(key, { at: Date.now(), value });
      }
      return value;
    })
    .finally(() => {
      if (workspaceInflight.get(key) === task) workspaceInflight.delete(key);
    });
  workspaceInflight.set(key, task);
  return task;
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
