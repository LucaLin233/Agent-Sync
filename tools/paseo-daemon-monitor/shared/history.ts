/**
 * History windowing for the detail charts. Pure: the client passes the samples
 * the daemon returned and gets back polyline runs already cut at nulls and at
 * gaps. Each point's `x` is 0..1 across the window, `v` is the raw value.
 */

export interface TimePoint {
  at: string;
}

export type SeriesRun = { x: number; v: number }[];

export const CHART_WINDOW_MS = 3 * 60_000;

/**
 * Cut a series into runs. A sample breaks the line when its value is missing,
 * when its timestamp is unparsable, or when the gap to the previous kept sample
 * is longer than `maxGapMs` (an idle stop leaves a visible hole).
 */
export function buildSeries<T extends TimePoint>(
  samples: readonly T[],
  value: (sample: T) => number | null | undefined,
  endMs: number,
  windowMs: number = CHART_WINDOW_MS,
  maxGapMs: number = 6_000,
): SeriesRun[] {
  const startMs = endMs - windowMs;
  const runs: SeriesRun[] = [];
  let run: SeriesRun | null = null;
  let previousMs: number | null = null;

  for (const sample of samples) {
    const at = Date.parse(sample.at);
    if (Number.isNaN(at)) {
      run = null;
      previousMs = null;
      continue;
    }
    if (at < startMs || at > endMs) continue;
    const numeric = value(sample);
    if (numeric === null || numeric === undefined || !Number.isFinite(numeric)) {
      run = null;
      previousMs = at;
      continue;
    }
    if (previousMs !== null && at - previousMs > maxGapMs) run = null;
    previousMs = at;
    const point = { x: (at - startMs) / windowMs, v: numeric };
    if (!run) {
      run = [];
      runs.push(run);
    }
    run.push(point);
  }
  return runs;
}

/** Number of points that would be drawn (used for the "waiting" placeholder). */
export function drawnPoints(runs: readonly SeriesRun[]): number {
  return runs.reduce((total, run) => total + run.length, 0);
}
