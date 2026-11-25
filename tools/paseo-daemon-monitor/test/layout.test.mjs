import assert from "node:assert/strict";
import test from "node:test";

import {
  chooseFooterPlan,
  columnWidthFor,
  FOOTER_BORDER_X,
  FOOTER_COL_PAD_X,
  FOOTER_ICON_GAP,
  FOOTER_COMPACT_RATE_FALLBACK,
  FOOTER_COMPACT_TAIL_PAD,
  FOOTER_ICON_SIZE,
  FOOTER_METER_MIN,
  FOOTER_METER_MIN_WIDTH,
  FOOTER_NETWORK_MIN_WIDTH,
  FOOTER_PAD_X,
  FOOTER_SLOTS,
  FOOTER_TAIL_MAX,
  FOOTER_TIME_MIN_WIDTH,
  tailBudget,
} from "../shared/layout.ts";

const base = { networkAvailable: true, showNetworkSetting: true, compact: false };
// "100%" at 11 px bold tabular digits. Uneven values prove a column is sized by
// the widest label, not by the sum of all three.
const widest = [40, 40, 40];
const uneven = [27, 40, 34];

test("tail track is clamp(W - 368, 0, 112)", () => {
  assert.equal(tailBudget(180), 0);
  assert.equal(tailBudget(368), 0);
  assert.equal(tailBudget(416), 48);
  assert.equal(tailBudget(480), 112);
  assert.equal(tailBudget(600), FOOTER_TAIL_MAX);
  assert.equal(tailBudget(900), FOOTER_TAIL_MAX);
});

test("three equal columns span the inner width after the reserved tail", () => {
  const plan = chooseFooterPlan({ ...base, width: 600, textWidths: uneven });
  assert.equal(plan.tailWidth, 112);
  assert.equal(plan.columnWidth, (600 - FOOTER_PAD_X * 2 - FOOTER_BORDER_X - 112) / FOOTER_SLOTS);
  // Equal columns do not depend on how wide each label is.
  for (const other of [
    chooseFooterPlan({ ...base, width: 600, textWidths: [12, 40, 33] }),
    chooseFooterPlan({ ...base, width: 600, textWidths: [0, 0, 0] }),
  ]) {
    assert.equal(other.columnWidth, plan.columnWidth);
  }
});

test("columns stay put at 415/416 and 479/480 while the tail swaps content", () => {
  const before416 = chooseFooterPlan({ ...base, width: FOOTER_TIME_MIN_WIDTH - 1, textWidths: widest });
  const at416 = chooseFooterPlan({ ...base, width: FOOTER_TIME_MIN_WIDTH, textWidths: widest });
  // The track is reserved from 368 DP and grows 1:1 with the row, so revealing
  // the clock at 416 does not re-flow anything: only the content appears.
  assert.equal(before416.tailWidth + 1, at416.tailWidth);
  assert.ok(Math.abs(before416.columnWidth - at416.columnWidth) < 1);
  assert.equal(before416.showTail, false);
  assert.equal(at416.showTail, true);
  assert.equal(at416.tail, "time");

  const before480 = chooseFooterPlan({ ...base, width: FOOTER_NETWORK_MIN_WIDTH - 1, textWidths: widest });
  const at480 = chooseFooterPlan({ ...base, width: FOOTER_NETWORK_MIN_WIDTH, textWidths: widest });
  // Same continuous growth at the 480 switch; only the tail's content changes.
  assert.ok(Math.abs(before480.columnWidth - at480.columnWidth) < 1);
  assert.equal(before480.tailWidth + 1, at480.tailWidth);
  assert.equal(before480.tail, "time");
  assert.equal(at480.tail, "network");
  // Mode, icon size and meter length are identical across the content swap.
  assert.equal(before480.mode, at480.mode);
  assert.equal(before480.iconSize, at480.iconSize);
  assert.equal(before480.meterWidth, at480.meterWidth);
});

test("the meter length grows with the sidebar from the first eligible width", () => {
  const widths = [480, 600, 700, 900, 1200];
  const plans = widths.map((width) => chooseFooterPlan({ ...base, width, textWidths: widest }));
  for (let index = 1; index < plans.length; index += 1) {
    assert.ok(plans[index].meterWidth > plans[index - 1].meterWidth, `meter must grow at ${widths[index]}`);
  }
  // 480 DP has 116.67 DP of column with a 40 DP number: the meter is small but real.
  assert.ok(plans[0].meterWidth >= FOOTER_METER_MIN);
  assert.ok(plans[0].meterWidth < 60);
});

test("a wide sidebar shows a long meter, not a fixed stub", () => {
  const wide = chooseFooterPlan({ ...base, width: 900, textWidths: widest });
  const column = wide.columnWidth - FOOTER_COL_PAD_X * 2;
  assert.equal(wide.meterWidth, column - (FOOTER_ICON_SIZE + FOOTER_ICON_GAP + 40) - FOOTER_ICON_GAP);
  assert.ok(wide.meterWidth > 80);
});

test("narrow rows keep the icons and the full percentages, meters and tail hidden", () => {
  for (const width of [180, 200, 248]) {
    const plan = chooseFooterPlan({ ...base, width, textWidths: widest });
    assert.equal(plan.showMeters, false, `width ${width}`);
    assert.equal(plan.meterWidth, 0, `width ${width}`);
    assert.equal(plan.showTail, false, `width ${width}`);
    assert.equal(plan.showIcons, true, `width ${width}`);
    assert.notEqual(plan.mode, "content", `width ${width}`);
  }
  // 200 DP is below the 248 DP meter cutoff and inside the stacked icon tier.
  assert.equal(chooseFooterPlan({ ...base, width: 200, textWidths: widest }).mode, "stacked");
  // The host's compact layout no longer bans meters by itself: leftover space
  // in a phone row is used, and the compact tier still needs 14 DP of leftover.
  const compact = chooseFooterPlan({ ...base, width: 900, compact: true, textWidths: widest });
  assert.equal(compact.showMeters, true);
  assert.ok(compact.meterWidth >= FOOTER_METER_MIN);
  assert.equal(compact.showIcons, true);
  // Past the design's 248 DP container threshold the meter comes back even
  // though the track is only a dozen DP long; it then grows with the row.
  const at300 = chooseFooterPlan({ ...base, width: 300, textWidths: widest });
  assert.equal(at300.showMeters, true);
  assert.ok(at300.meterWidth >= 14 && at300.meterWidth < 40);
});

test("the icon + number tier is sized by the widest label, not the sum", () => {
  const narrowestRow = (widestLabel) =>
    FOOTER_PAD_X * 2 + FOOTER_BORDER_X + FOOTER_SLOTS * (2 * FOOTER_COL_PAD_X + FOOTER_ICON_SIZE + FOOTER_ICON_GAP + widestLabel);
  assert.equal(chooseFooterPlan({ ...base, width: narrowestRow(40), textWidths: widest }).mode, "row");
  assert.equal(chooseFooterPlan({ ...base, width: narrowestRow(40), textWidths: uneven }).mode, "row");
  assert.equal(chooseFooterPlan({ ...base, width: narrowestRow(40) - 0.5, textWidths: widest }).mode, "stacked");
});

test("an unmeasured first frame keeps icons, flex columns and no decorations", () => {
  const plan = chooseFooterPlan({ ...base, width: null, textWidths: [null, null, null] });
  assert.equal(plan.measured, false);
  assert.equal(plan.showMeters, false);
  assert.equal(plan.showTail, false);
  assert.equal(plan.showIcons, true);
  assert.equal(plan.mode, "row");
});

test("the footer switch only swaps the tail: rates never displace the columns", () => {
  const on = chooseFooterPlan({ ...base, width: 900, textWidths: widest });
  const off = chooseFooterPlan({ ...base, width: 900, showNetworkSetting: false, textWidths: widest });
  assert.equal(on.tail, "network");
  assert.equal(off.tail, "time");
  assert.equal(on.columnWidth, off.columnWidth);
  assert.equal(on.meterWidth, off.meterWidth);
  // A host without a network counter falls back to the clock at the same width.
  assert.equal(chooseFooterPlan({ ...base, width: 900, networkAvailable: false, textWidths: widest }).tail, "time");
});

test("the layout derives column width consistently for callers", () => {
  for (const width of [180, 416, 480, 600, 900]) {
    assert.equal(columnWidthFor(width), chooseFooterPlan({ ...base, width, textWidths: widest }).columnWidth);
  }
  assert.ok(FOOTER_METER_MIN_WIDTH < FOOTER_TIME_MIN_WIDTH);
  assert.equal(chooseFooterPlan({ ...base, width: FOOTER_METER_MIN_WIDTH - 1, textWidths: widest }).showMeters, false);
});

// --- Compact (phone) four-zone footer ---------------------------------------
// No live measurement is used for the budget; it comes from the fixed label
// size and the font scale, so a changing reading cannot re-flow the row.
const compactBase = { networkAvailable: true, showNetworkSetting: true, compact: true };
const RATE_TAIL = FOOTER_COMPACT_RATE_FALLBACK + FOOTER_COMPACT_TAIL_PAD; // reserved rate + separator

test("phone widths 350/368/390/424 show both rates and keep icon + full number", () => {
  for (const width of [350, 365, 368, 390, 400, 424]) {
    const plan = chooseFooterPlan({ ...compactBase, width, textWidths: widest });
    assert.equal(plan.showTail, true, `tail at ${width}`);
    assert.equal(plan.tail, "network", `rates at ${width}`);
    assert.equal(plan.tailStacked, true, `rates stack on two lines at ${width}`);
    assert.equal(plan.tailWidth, RATE_TAIL, `tail budget at ${width}`);
    assert.equal(plan.showIcons, true, `icons at ${width}`);
    assert.equal(plan.mode, "row", `one line at ${width}`);
    // Space between chrome, the tail and the three equal columns.
    const expected = (width - FOOTER_PAD_X * 2 - FOOTER_BORDER_X - RATE_TAIL) / FOOTER_SLOTS;
    assert.ok(Math.abs(plan.columnWidth - expected) < 1e-9, `columns at ${width}`);
    assert.ok(plan.meterWidth >= FOOTER_METER_MIN, `meter at ${width}`);
  }
});

test("the phone footer drops the rate group before it would clip a percentage", () => {
  // Largest width that still fits icon + number in every column with the tail.
  const needs = FOOTER_ICON_SIZE + FOOTER_ICON_GAP + 40;
  const minWithTail = FOOTER_PAD_X * 2 + FOOTER_BORDER_X + RATE_TAIL + FOOTER_SLOTS * (needs + FOOTER_COL_PAD_X * 2);
  const at = chooseFooterPlan({ ...compactBase, width: minWithTail + 0.5, textWidths: widest });
  const below = chooseFooterPlan({ ...compactBase, width: minWithTail - 0.5, textWidths: widest });
  assert.equal(at.tail, "network");
  assert.equal(at.mode, "row");
  assert.equal(below.tail, "none");
  assert.equal(below.tailWidth, 0);
  assert.equal(below.showTail, false);
  // With the tail gone the space goes back to the three columns, never an
  // empty reserve: columns are strictly wider and the numbers still fit.
  assert.ok(below.columnWidth > at.columnWidth);
  assert.equal(below.mode, "row");
});

test("phone: switch off or no sample returns the tail space, and never a clock", () => {
  const on = chooseFooterPlan({ ...compactBase, width: 400, textWidths: widest });
  const off = chooseFooterPlan({ ...compactBase, width: 400, showNetworkSetting: false, textWidths: widest });
  const none = chooseFooterPlan({ ...compactBase, width: 400, networkAvailable: false, textWidths: widest });
  for (const plan of [off, none]) {
    assert.equal(plan.tail, "none");
    assert.equal(plan.tailWidth, 0);
    assert.equal(plan.showTail, false);
    assert.ok(plan.columnWidth > on.columnWidth);
    // A phone never shows the sample time in the footer; it lives in detail.
    assert.notEqual(plan.tail, "time");
  }
});

test("a large font scale widens the phone rate budget and can drop it", () => {
  const fs1 = chooseFooterPlan({ ...compactBase, width: 400, textWidths: widest, fontScale: 1 });
  const fs2 = chooseFooterPlan({ ...compactBase, width: 400, textWidths: widest, fontScale: 2 });
  assert.equal(fs1.tail, "network");
  assert.equal(fs1.tailWidth, FOOTER_COMPACT_RATE_FALLBACK + FOOTER_COMPACT_TAIL_PAD);
  assert.ok(fs2.tailWidth >= fs1.tailWidth);
  assert.equal(fs2.tailWidth, FOOTER_COMPACT_RATE_FALLBACK * 2 + FOOTER_COMPACT_TAIL_PAD);
  // The budget depends only on the font scale, never on the digits drawn, so a
  // reading changing from `9.1K` to `2.4M` (or back) cannot move the columns.
  const again = chooseFooterPlan({ ...compactBase, width: 400, textWidths: widest, fontScale: 1 });
  assert.equal(again.tailWidth, fs1.tailWidth);
  assert.equal(again.columnWidth, fs1.columnWidth);
});

test("desktop keeps its anchors and never stacks rates", () => {
  const at480 = chooseFooterPlan({ ...base, width: 480, textWidths: widest });
  assert.equal(at480.tail, "network");
  assert.equal(at480.tailStacked, false);
  assert.equal(at480.tailWidth, 112);
  const at416 = chooseFooterPlan({ ...base, width: 416, textWidths: widest });
  assert.equal(at416.tail, "time");
  assert.equal(at416.tailStacked, false);
});

test("the phone rate group's exact minimum width is reported and monotone", () => {
  // Smallest outer width where the three groups still fit icon + full number
  // next to the two-line rate group, at the widest 40 DP label and 36 DP rate.
  const needs = FOOTER_ICON_SIZE + FOOTER_ICON_GAP + 40;
  const min = FOOTER_PAD_X * 2 + FOOTER_BORDER_X + RATE_TAIL + FOOTER_SLOTS * (needs + FOOTER_COL_PAD_X * 2);
  assert.ok(min < 350, `min ${min} must sit below the smallest phone width`);
  const atMin = chooseFooterPlan({ ...compactBase, width: min, textWidths: widest });
  assert.equal(atMin.tail, "network");
  assert.equal(atMin.mode, "row");
  assert.equal(atMin.showMeters, false); // exactly enough for numbers, no meter
  assert.equal(chooseFooterPlan({ ...compactBase, width: min - 1, textWidths: widest }).tail, "none");
  // At 350 DP there is real meter room left over.
  assert.ok(chooseFooterPlan({ ...compactBase, width: 350, textWidths: widest }).meterWidth >= FOOTER_METER_MIN);
});

test("desktop keeps the clock when two inline rates cannot fit the font-scaled budget", () => {
  // 2 x 56 DP labels + gap + padding needs 127 DP; the 112 DP cap cannot hold it.
  const big = chooseFooterPlan({ width: 900, textWidths: widest, networkAvailable: true, showNetworkSetting: true, compact: false, fontScale: 1.5 });
  assert.equal(big.tailWidth, FOOTER_TAIL_MAX);
  assert.equal(big.tail, "time");
  // Normal scale fits with room to spare.
  const normal = chooseFooterPlan({ width: 900, textWidths: widest, networkAvailable: true, showNetworkSetting: true, compact: false, fontScale: 1 });
  assert.equal(normal.tail, "network");
  assert.equal(normal.tailStacked, false);
});

test("phone at an extreme font scale drops the rates instead of clipping numbers", () => {
  const bigLabels = [80, 80, 80];
  const plan = chooseFooterPlan({ width: 350, textWidths: bigLabels, networkAvailable: true, showNetworkSetting: true, compact: true, fontScale: 2 });
  assert.equal(plan.tail, "none");
  assert.equal(plan.tailWidth, 0);
  assert.equal(plan.showIcons, true);
  assert.notEqual(plan.mode, "content");
  // The space went back to the columns rather than staying reserved.
  assert.ok(plan.columnWidth > (350 - FOOTER_PAD_X * 2 - FOOTER_BORDER_X) / FOOTER_SLOTS - 1e-9);
});

test("phone: a moderately larger font still shows both rates at 390 DP", () => {
  const labels = [52, 52, 52]; // 1.3x of the 40 DP reference label
  const plan = chooseFooterPlan({ width: 390, textWidths: labels, networkAvailable: true, showNetworkSetting: true, compact: true, fontScale: 1.3 });
  assert.equal(plan.tail, "network");
  assert.equal(plan.mode, "row");
  assert.equal(plan.showIcons, true);
  assert.equal(plan.tailWidth, Math.ceil(40 * 1.3) + FOOTER_COMPACT_TAIL_PAD);
});
