import assert from "node:assert/strict";
import test from "node:test";

import {
  chooseFooterPlan,
  columnWidthFor,
  FOOTER_BORDER_X,
  FOOTER_COL_PAD_X,
  FOOTER_ICON_GAP,
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
  // The host's compact layout retracts meters even when the width would fit.
  const compact = chooseFooterPlan({ ...base, width: 900, compact: true, textWidths: widest });
  assert.equal(compact.showMeters, false);
  assert.equal(compact.meterWidth, 0);
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
