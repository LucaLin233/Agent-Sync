import assert from "node:assert/strict";
import test from "node:test";

import { buildSeries, CHART_WINDOW_MS, drawnPoints } from "../shared/history.ts";

const at = (ms) => new Date(ms).toISOString();
const END = Date.parse("2030-09-18T14:32:00.000Z");

function sample(offsetMs, value) {
  return { at: at(END + offsetMs), v: value };
}

test("a series is cut at null values and never bridges them", () => {
  const samples = [
    sample(-6000, 10),
    sample(-4000, 20),
    sample(-2000, null),
    sample(0, 30),
  ];
  const runs = buildSeries(samples, (point) => point.v, END);
  assert.deepEqual(runs.map((run) => run.map((point) => point.v)), [[10, 20], [30]]);
  assert.equal(drawnPoints(runs), 3);
});

test("a gap longer than the cadence tolerance starts a new run", () => {
  const samples = [sample(-60_000, 40), sample(-58_000, 45), sample(-10_000, 50), sample(-8_000, 55)];
  const runs = buildSeries(samples, (point) => point.v, END, CHART_WINDOW_MS, 6000);
  assert.deepEqual(runs.map((run) => run.map((point) => point.v)), [[40, 45], [50, 55]]);
});

test("points outside the three-minute window are dropped and x spans 0..1", () => {
  const samples = [
    sample(-CHART_WINDOW_MS - 2000, 99),
    sample(-CHART_WINDOW_MS, 5),
    sample(-CHART_WINDOW_MS + 2000, 15),
    sample(0, 50),
  ];
  const [run, tail] = buildSeries(samples, (point) => point.v, END);
  assert.deepEqual(run.map((point) => point.v), [5, 15]);
  assert.equal(run[0].x, 0);
  // The old point is gone; the last in-window point sits at x = 1.
  assert.deepEqual(tail.map((point) => point.v), [50]);
  assert.equal(tail[0].x, 1);
});

test("unparsable timestamps are a hole, not a point", () => {
  const samples = [{ at: "nope", v: 10 }, sample(-2000, 20), sample(0, 30)];
  const runs = buildSeries(samples, (point) => point.v, END);
  assert.deepEqual(runs.map((run) => run.map((point) => point.v)), [[20, 30]]);
});

test("an empty history yields no runs", () => {
  assert.deepEqual(buildSeries([], () => 1, END), []);
  assert.equal(drawnPoints([]), 0);
});
