import assert from "node:assert/strict";
import test from "node:test";

import {
  chooseFooterLayout,
  columnWidth,
  FOOTER_ANOMALY_DOT,
  FOOTER_ANOMALY_GAP,
  FOOTER_COL_GAP,
  FOOTER_COL_GAP_TIGHT,
  FOOTER_ICON_GAP,
  FOOTER_ICON_GAP_TIGHT,
  FOOTER_ICON_SIZE,
  FOOTER_ICON_SIZE_TIGHT,
  FOOTER_PAD_X,
  FOOTER_PAD_X_TIGHT,
  FOOTER_SLOTS,
  FOOTER_STYLES,
  frameInset,
  rowWidth,
  textOnlyWidth,
} from "../shared/layout.ts";

const base = { compact: false, anomaly: false, anomalyTextWidth: 0 };
// "100.0%" and "100%" are the widest realistic readings; 40 DP is a generous
// measurement for them at 11 px bold tabular digits.
const widest = [40, 40, 40];
const uneven = [30, 40, 34];

test("column width is the widest label plus decoration, never the sum", () => {
  const normal = FOOTER_STYLES[0];
  assert.equal(columnWidth(uneven, normal), 40 + FOOTER_ICON_SIZE + FOOTER_ICON_GAP + 26);
  const stacked = FOOTER_STYLES[3];
  assert.equal(columnWidth(uneven, stacked), 40);
  const tinyLabel = [12, 12, 12];
  // A very short label still reserves the icon width on its own row.
  assert.equal(columnWidth(tinyLabel, stacked), FOOTER_ICON_SIZE);
});

test("row width is three equal columns plus chrome", () => {
  const style = FOOTER_STYLES[1]; // icons, no meter
  const expected = frameInset(style.paddingX) + FOOTER_SLOTS * columnWidth(uneven, style) + style.columnGap * (FOOTER_SLOTS - 1);
  assert.equal(rowWidth(uneven, style), expected);
  assert.equal(FOOTER_SLOTS, 3);
});

test("100.0% readings keep icons at the host's 200 DP minimum sidebar width", () => {
  const plan = chooseFooterLayout({ ...base, availableWidth: 200, textWidths: widest });
  assert.notEqual(plan.mode, "content");
  assert.equal(plan.showIcons, true);
  assert.equal(plan.showMeters, false);
  // Must be the tightest row or the stacked tier, both of which fit at 200 DP.
  assert.ok(plan.mode === "row" || plan.mode === "stacked");
  assert.ok(plan.paddingX <= FOOTER_PAD_X_TIGHT);
  assert.ok(plan.iconSize <= FOOTER_ICON_SIZE_TIGHT);
});

test("meters return as soon as the widest tier fits, exact boundary included", () => {
  const threshold = rowWidth(widest, FOOTER_STYLES[0]);
  const at = chooseFooterLayout({ ...base, availableWidth: threshold, textWidths: widest });
  assert.equal(at.showMeters, true);
  assert.equal(at.mode, "row");
  const below = chooseFooterLayout({ ...base, availableWidth: threshold - 0.1, textWidths: widest });
  assert.equal(below.showMeters, false);
  assert.equal(below.showIcons, true);
});

test("compact layout never paints meters but keeps icons and equal columns", () => {
  const plan = chooseFooterLayout({ ...base, compact: true, availableWidth: 200, textWidths: widest });
  assert.equal(plan.showMeters, false);
  assert.equal(plan.showIcons, true);
  assert.notEqual(plan.mode, "content");
});

test("tiers only shrink padding, gap and icon size, and only stack as a last row resort", () => {
  const sizes = FOOTER_STYLES.map((style) => rowWidth(widest, style));
  for (let i = 1; i < sizes.length; i += 1) {
    assert.ok(sizes[i] <= sizes[i - 1], `tier ${i} must not be wider than tier ${i - 1}`);
  }
  assert.equal(FOOTER_STYLES[3].stacked, true);
  assert.ok(FOOTER_STYLES[2].paddingX < FOOTER_STYLES[1].paddingX);
  assert.ok(FOOTER_STYLES[2].iconSize < FOOTER_STYLES[1].iconSize);
  assert.ok(FOOTER_STYLES[2].columnGap < FOOTER_STYLES[1].columnGap);
  assert.ok(FOOTER_STYLES[2].iconGap < FOOTER_STYLES[1].iconGap);
});

test("the smallest sidebar that still shows icon + number vertically is reported", () => {
  const stacked = FOOTER_STYLES[3];
  const need = rowWidth(widest, stacked);
  const at = chooseFooterLayout({ ...base, availableWidth: need, textWidths: widest });
  assert.equal(at.mode, "stacked");
  assert.equal(at.showIcons, true);
  const below = chooseFooterLayout({ ...base, availableWidth: need - 0.1, textWidths: widest });
  assert.equal(below.mode, "content");
  assert.equal(below.showIcons, false);
  // 100.0% at three equal stacked columns must fit inside 200 DP: the floors
  // are 3 x 40 DP of text plus 2 x 2 DP gaps plus 2 x 4 DP padding and 2 px border.
  assert.equal(need, 2 * FOOTER_PAD_X_TIGHT + 2 + 3 * 40 + 2 * FOOTER_COL_GAP_TIGHT);
  assert.ok(need <= 200);
});

test("extremely narrow rows fall back to numbers only, never ellipsized", () => {
  // Three 40 DP numbers plus tight chrome are the physical floor (134 DP).
  const floor = textOnlyWidth(widest, true);
  assert.equal(floor, 8 + 2 + 120 + 2 * FOOTER_COL_GAP_TIGHT);
  // At the floor the stacked tier still fits and is preferred, since it keeps
  // all three icons. Only below it do the icons have to go.
  const atFloor = chooseFooterLayout({ ...base, availableWidth: floor, textWidths: widest });
  assert.equal(atFloor.mode, "stacked");
  assert.equal(atFloor.showIcons, true);
  const below = chooseFooterLayout({ ...base, availableWidth: floor - 0.1, textWidths: widest });
  assert.equal(below.mode, "content");
  assert.equal(below.showIcons, false);
  assert.equal(below.showMeters, false);
  assert.equal(below.tightGap, true);
});

test("an unmeasured first frame keeps icons and never paints a meter", () => {
  const plan = chooseFooterLayout({ availableWidth: null, compact: false, textWidths: [null, null, null], anomaly: false, anomalyTextWidth: 0 });
  assert.equal(plan.showMeters, false);
  assert.equal(plan.showIcons, true);
  assert.notEqual(plan.mode, "content");
});

test("an anomaly never displaces the main reading: words, then dot, then nothing", () => {
  const words = 30;
  const style = FOOTER_STYLES[1];
  const slack = style.columnGap + FOOTER_ANOMALY_GAP + words;
  const noMeterRow = rowWidth(widest, style);
  const withWords = chooseFooterLayout({ ...base, availableWidth: noMeterRow + slack, textWidths: widest, anomaly: true, anomalyTextWidth: words });
  assert.equal(withWords.showAnomalyText, true);
  assert.equal(withWords.showAnomalyMark, true);

  const dot = chooseFooterLayout({ ...base, availableWidth: noMeterRow + style.columnGap + FOOTER_ANOMALY_GAP + FOOTER_ANOMALY_DOT, textWidths: widest, anomaly: true, anomalyTextWidth: words });
  assert.equal(dot.showAnomalyText, false);
  assert.equal(dot.showAnomalyMark, true);

  const none = chooseFooterLayout({ ...base, availableWidth: noMeterRow + style.columnGap + FOOTER_ANOMALY_GAP + FOOTER_ANOMALY_DOT - 0.1, textWidths: widest, anomaly: true, anomalyTextWidth: words });
  assert.equal(none.showAnomalyText, false);
  assert.equal(none.showAnomalyMark, false);
  assert.notEqual(none.mode, "content");
});

test("network rates join only when the three widest columns and the group both fit", () => {
  const style = FOOTER_STYLES[0]; // meters
  const threeColumns = rowWidth(widest, style);
  const withNet = threeColumns + 10 + 92;
  const at = chooseFooterLayout({ ...base, availableWidth: withNet, textWidths: widest });
  assert.equal(at.showNetwork, true);
  assert.equal(at.showMeters, true);
  const below = chooseFooterLayout({ ...base, availableWidth: withNet - 0.1, textWidths: widest });
  assert.equal(below.showNetwork, false);
  // The three readings never lose their meter tier to make room for rates.
  assert.equal(below.showMeters, true);
});

test("a 480 DP sidebar reaches the rate tier while the narrow tiers never do", () => {
  const narrow = chooseFooterLayout({ ...base, availableWidth: 200, textWidths: widest });
  assert.equal(narrow.showNetwork, false);
  assert.equal(narrow.showIcons, true);
  const wide = chooseFooterLayout({ ...base, availableWidth: 480, textWidths: widest });
  assert.equal(wide.showNetwork, true);
  assert.equal(wide.showMeters, true);
});

test("an anomaly takes precedence over the rate group at equal width", () => {
  const style = FOOTER_STYLES[0];
  const threeColumns = rowWidth(widest, style);
  const words = 30;
  const need = threeColumns + 10 + 92;
  const plan = chooseFooterLayout({ ...base, availableWidth: need, textWidths: widest, anomaly: true, anomalyTextWidth: words });
  // Either both fit, or rates drop so the badge keeps its room; never clipped.
  if (plan.showNetwork) {
    assert.ok(need >= threeColumns + 10 + 92 + style.columnGap + FOOTER_ANOMALY_GAP + words);
  } else {
    assert.ok(need >= threeColumns + style.columnGap + FOOTER_ANOMALY_GAP + words);
  }
  assert.equal(plan.showAnomalyText, true);
});
