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

export function formatCachePillLabel(rate: number | null | undefined): string {
  return "缓存 " + formatCacheRate(rate);
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
  | { kind: "start" | "assistant" | "failed" | "canceled"; turnId: string; timestamp: number }
  | { kind: "completed"; turnId: string; timestamp: number; outputTokens: number | null }
  | { kind: "gap" }
  | { kind: "replacement" };

export interface TurnMeasurement {
  turnId: string;
  firstAssistantMs: number | null;
  elapsedMs: number;
  outcome: "completed" | "failed" | "canceled";
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
      firstAssistantMs: active.firstAssistantAt === null
        ? null
        : active.firstAssistantAt - active.startedAt,
      elapsedMs,
      outcome: signal.kind,
      outputPerSecond,
    },
  };
}
