export interface ReportedUsage {
  inputTokens?: number;
  cachedInputTokens?: number;
  outputTokens?: number;
  contextWindowUsedTokens?: number;
  contextWindowMaxTokens?: number;
}

export interface CacheSample {
  input: number;
  cached: number;
}

export function tokenCount(value: number | undefined): number | null {
  return value !== undefined && Number.isSafeInteger(value) && value >= 0 ? value : null;
}

/** In 0.17.1, Codex reports its latest request. Its input already includes cache reads. */
export function latestCacheSample(
  provider: string,
  usage: ReportedUsage | null | undefined,
  persistenceProvider?: unknown,
): CacheSample | null {
  if (provider !== "codex" && persistenceProvider !== "codex") return null;
  const input = tokenCount(usage?.inputTokens);
  const cached = tokenCount(usage?.cachedInputTokens);
  if (input === null || input === 0 || cached === null || cached > input) return null;
  return { input, cached };
}

export interface CacheSummary {
  input: number;
  cached: number;
  covered: number;
  rate: number | null;
}

const cachePercent = new Intl.NumberFormat("zh-CN", {
  style: "percent",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

/** The one format shared by the panel and the composer pill. */
export function formatCacheRate(rate: number | null | undefined): string {
  return rate === null || rate === undefined || !Number.isFinite(rate) ? "—" : cachePercent.format(rate);
}

/** One latest sample per conversation. Repeated snapshots are never added over time. */
export function summarizeLatestSamples(samples: readonly (CacheSample | null)[]): CacheSummary {
  let input = 0;
  let cached = 0;
  let covered = 0;
  for (const sample of samples) {
    if (sample === null) continue;
    input += sample.input;
    cached += sample.cached;
    covered += 1;
  }
  return {
    input,
    cached,
    covered,
    rate: input > 0 && Number.isSafeInteger(input) ? cached / input : null,
  };
}

export type TurnSignal =
  | { kind: "start" | "failed" | "canceled"; turnId: string; timestamp: number }
  | { kind: "assistant"; turnId: string; timestamp: number; visible: boolean }
  | { kind: "completed"; turnId: string; timestamp: number; outputTokens: number | null }
  | { kind: "gap" }
  | { kind: "replacement" };

export interface TurnMeasurement {
  turnId: string;
  /** First assistant event with non-blank visible text; never a provider TTFT. */
  firstVisibleMs: number | null;
  elapsedMs: number;
  outcome: "completed" | "failed" | "canceled";
  /** Only when that same turn reported a usable output count (Claude). */
  outputPerSecond: number | null;
}

export interface TurnObservation {
  active: { id: string; startedAt: number; firstAssistantAt: number | null } | null;
  last: TurnMeasurement | null;
}

export function observeTurn(state: TurnObservation, signal: TurnSignal): TurnObservation {
  switch (signal.kind) {
    case "gap":
      return { ...state, active: null };
    case "replacement":
      return { active: null, last: null };
  }
  if (!Number.isFinite(signal.timestamp)) return state;
  const active = state.active;
  if (signal.kind === "start") {
    if (active?.id === signal.turnId || state.last?.turnId === signal.turnId) return state;
    return {
      ...state,
      active: { id: signal.turnId, startedAt: signal.timestamp, firstAssistantAt: null },
    };
  }
  if (active?.id !== signal.turnId) return state;
  if (signal.kind === "assistant") {
    if (active.firstAssistantAt !== null || signal.timestamp < active.startedAt) return state;
    // Only a boolean projection of the item text is kept; the message text
    // itself never enters observation state.
    if (!signal.visible) return state;
    return { ...state, active: { ...active, firstAssistantAt: signal.timestamp } };
  }
  if (signal.timestamp < (active.firstAssistantAt ?? active.startedAt)) {
    return { ...state, active: null };
  }
  const elapsedMs = signal.timestamp - active.startedAt;
  const outputPerSecond = signal.kind === "completed" && signal.outputTokens !== null && elapsedMs > 0
    ? signal.outputTokens * 1_000 / elapsedMs
    : null;
  return {
    active: null,
    last: {
      turnId: signal.turnId,
      firstVisibleMs: active.firstAssistantAt === null
        ? null
        : active.firstAssistantAt - active.startedAt,
      elapsedMs,
      outcome: signal.kind,
      outputPerSecond,
    },
  };
}

/** Tokens per second from one turn's output count and whole-turn duration. */
export function tokensPerSecond(
  outputTokens: number | null | undefined,
  elapsedMs: number | null | undefined,
): number | null {
  if (outputTokens === null || outputTokens === undefined || !Number.isSafeInteger(outputTokens) || outputTokens < 0) return null;
  if (elapsedMs === null || elapsedMs === undefined || !Number.isFinite(elapsedMs) || elapsedMs <= 0) return null;
  return outputTokens * 1_000 / elapsedMs;
}

const speedFormat = new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

/** The exact one-decimal number used by panel headlines and tooltips. */
export function formatTokenSpeedNumber(value: number | null | undefined): string {
  return value === null || value === undefined || !Number.isFinite(value) ? "—" : speedFormat.format(value);
}

/** One decimal, shared by the panel details, tooltip and composer pill. */
export function formatTokenSpeed(value: number | null | undefined, unit: "short" | "full" = "short"): string {
  const formatted = formatTokenSpeedNumber(value);
  return formatted === "—" ? formatted : formatted + (unit === "full" ? " token/s" : " t/s");
}

/**
 * One of the composer pill's two cache slots. A slot is never filled from the
 * other basis: `unavailable` carries why that reading is missing, and `loading`
 * means the read is still in flight. `ready` with a null rate is a finished
 * read that found no valid snapshot, which is distinct from zero.
 */
export type PillCacheBasis =
  | { kind: "loading" }
  | { kind: "unavailable"; reason: string }
  | { kind: "ready"; rate: number | null };

function pillRateText(slot: PillCacheBasis): string {
  if (slot.kind === "loading") return "…";
  if (slot.kind === "unavailable") return "—";
  return formatCacheRate(slot.rate);
}

/**
 * The composer pill shares one 160 px row with its icon, the pill padding and
 * any other pill, and the host truncates the label with an ellipsis, so the
 * visible line uses the shortest readable form of each rate. One-decimal
 * precision stays; a whole percentage drops only the trailing `.0`
 * (`100.0%` → `100%`) so two full rates still fit. The tooltip keeps the full
 * names and one decimal.
 */
function pillRateCompact(slot: PillCacheBasis): string {
  const text = pillRateText(slot);
  return text.endsWith(".0%") ? text.slice(0, -3) + "%" : text;
}

function pillTitleText(slot: PillCacheBasis, label: string, missing: string): string {
  if (slot.kind === "loading") return label + " …";
  if (slot.kind === "unavailable") return label + " —（" + slot.reason + "）";
  const rate = formatCacheRate(slot.rate);
  return rate === "—" ? label + " —（" + missing + "）" : label + " " + rate;
}

/**
 * Visible composer-pill label: "总98.1%·近99.5%". The two percentages are
 * independent readings — the cumulative rate from the cumulative RPC, the
 * recent rate from each conversation's latest `lastUsage` — and neither ever
 * stands in for the other. `总`/`近` and the bare `·` are the shortest form that
 * still names both bases inside the host's 160 px single line; the tooltip
 * below spells out the full names and any missing-value reason.
 */
export function formatPillLabel(cumulative: PillCacheBasis, recent: PillCacheBasis): string {
  return "总" + pillRateCompact(cumulative) + "·近" + pillRateCompact(recent);
}

/** Full tooltip: open action, both cache bases, and why either one is missing. */
export function formatPillTitle(cumulative: PillCacheBasis, recent: PillCacheBasis): string {
  return "打开工作区用量 · "
    + pillTitleText(cumulative, "累计缓存", "尚无有效累计快照")
    + " · "
    + pillTitleText(recent, "最近样本", "尚无有效最近样本");
}

const countFormat = new Intl.NumberFormat("zh-CN");
const secondsFormat = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 });

export function formatTokenCount(value: number | null | undefined): string {
  return value === null || value === undefined || !Number.isSafeInteger(value) ? "—" : countFormat.format(value);
}

export function formatDurationMs(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value) || value < 0) return "—";
  return value < 1_000 ? countFormat.format(value) + " ms" : secondsFormat.format(value / 1_000) + " 秒";
}

/** A completed turn selected only by its own completion time. */
export interface CompletedTurnSample {
  completedAt: number;
  outputTokens: number | null;
  elapsedMs: number | null;
  firstTokenMs: number | null;
}

/** Newer wins even without a speed; an older faster turn never displaces it. */
export function latestCompletedTurn(
  current: CompletedTurnSample | null,
  candidate: CompletedTurnSample | null,
): CompletedTurnSample | null {
  if (!candidate) return current;
  if (!current || candidate.completedAt > current.completedAt) return candidate;
  return current;
}

/** Constant-space sums with independent denominators for speed and first token. */
export interface TurnTotals {
  /** Successful turns with a sane start and completion boundary. */
  completed: number;
  /** Turns contributing to the weighted speed (output delta and a positive duration). */
  speedSamples: number;
  outputTokens: number;
  elapsedMs: number;
  /** Turns with a reported first-token time, independent of output availability. */
  firstTokenSamples: number;
  firstTokenTotalMs: number;
}

export function emptyTurnTotals(): TurnTotals {
  return {
    completed: 0,
    speedSamples: 0,
    outputTokens: 0,
    elapsedMs: 0,
    firstTokenSamples: 0,
    firstTokenTotalMs: 0,
  };
}

export function addTurn(totals: TurnTotals, turn: CompletedTurnSample): TurnTotals {
  const output = turn.outputTokens;
  const elapsed = turn.elapsedMs;
  const canWeight = output !== null && elapsed !== null && elapsed > 0;
  return {
    completed: totals.completed + 1,
    speedSamples: totals.speedSamples + (canWeight ? 1 : 0),
    outputTokens: totals.outputTokens + (canWeight ? output : 0),
    elapsedMs: totals.elapsedMs + (canWeight ? elapsed : 0),
    firstTokenSamples: totals.firstTokenSamples + (turn.firstTokenMs !== null ? 1 : 0),
    firstTokenTotalMs: totals.firstTokenTotalMs + (turn.firstTokenMs ?? 0),
  };
}

export function mergeTurnTotals(left: TurnTotals, right: TurnTotals): TurnTotals {
  return {
    completed: left.completed + right.completed,
    speedSamples: left.speedSamples + right.speedSamples,
    outputTokens: left.outputTokens + right.outputTokens,
    elapsedMs: left.elapsedMs + right.elapsedMs,
    firstTokenSamples: left.firstTokenSamples + right.firstTokenSamples,
    firstTokenTotalMs: left.firstTokenTotalMs + right.firstTokenTotalMs,
  };
}

/** Weighted by whole-turn duration, never an average of per-turn rates. */
export function weightedTurnSpeed(totals: Pick<TurnTotals, "speedSamples" | "outputTokens" | "elapsedMs">): number | null {
  return totals.speedSamples > 0 && totals.elapsedMs > 0
    ? totals.outputTokens * 1_000 / totals.elapsedMs
    : null;
}

export function averageFirstTokenMs(
  totals: Pick<TurnTotals, "firstTokenSamples" | "firstTokenTotalMs">,
): number | null {
  return totals.firstTokenSamples > 0 ? totals.firstTokenTotalMs / totals.firstTokenSamples : null;
}
