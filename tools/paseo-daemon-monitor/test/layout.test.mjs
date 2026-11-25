import assert from "node:assert/strict";
import test from "node:test";

import {
  chooseFooterLayout,
  FOOTER_ANOMALY_DOT,
  FOOTER_ANOMALY_GAP,
  FOOTER_ICON_COST,
  FOOTER_METER_COST,
  FOOTER_ROW_GAP,
  FOOTER_ROW_GAP_TIGHT,
  iconWidth,
  meterWidth,
  textOnlyWidth,
} from "../shared/layout.ts";

// Three "99.9%"-sized labels; the numbers are whatever the platform measured.
const textWidths = [30, 30, 30];
const base = { compact: false, textWidths, anomaly: false, anomalyTextWidth: 0 };

test("thresholds are the exact outer widths that fit percentages, icons and meters", () => {
  assert.equal(textOnlyWidth(textWidths), 128);
  assert.equal(textOnlyWidth(textWidths, true), 118);
  assert.equal(iconWidth(textWidths), 176);
  assert.equal(meterWidth(textWidths), 254);
  assert.equal(FOOTER_ROW_GAP, 9);
  assert.equal(FOOTER_ROW_GAP_TIGHT, 4);
  assert.equal(FOOTER_ICON_COST, 16);
  assert.equal(FOOTER_METER_COST, 26);
});

test("meters appear only at or above their exact width, and only outside compact", () => {
  const at = chooseFooterLayout({ ...base, availableWidth: 254 });
  assert.equal(at.showMeters, true);
  assert.equal(at.showIcons, true);
  const below = chooseFooterLayout({ ...base, availableWidth: 253.9 });
  assert.equal(below.showMeters, false);
  assert.equal(below.showIcons, true);
  const compact = chooseFooterLayout({ ...base, availableWidth: 400, compact: true });
  assert.equal(compact.showMeters, false);
  assert.equal(compact.showIcons, true);
});

test("icons survive down to their own width and drop below it", () => {
  const at = chooseFooterLayout({ ...base, availableWidth: 176 });
  assert.equal(at.showIcons, true);
  assert.equal(at.tightGap, false);
  const below = chooseFooterLayout({ ...base, availableWidth: 175.9 });
  assert.equal(below.showIcons, false);
  assert.equal(below.tightGap, false);
});

test("percentages keep the normal gap until it physically no longer fits", () => {
  const at = chooseFooterLayout({ ...base, availableWidth: 128 });
  assert.equal(at.showIcons, false);
  assert.equal(at.tightGap, false);
  const below = chooseFooterLayout({ ...base, availableWidth: 127.9 });
  assert.equal(below.showIcons, false);
  assert.equal(below.tightGap, true);
});

test("an unmeasured first frame never paints a meter", () => {
  const plan = chooseFooterLayout({
    availableWidth: null,
    compact: false,
    textWidths: [null, null, null],
    anomaly: false,
    anomalyTextWidth: 0,
  });
  assert.equal(plan.showMeters, false);
  assert.equal(plan.showIcons, true);
});

test("an anomaly never displaces the numbers: words, then dot, then nothing", () => {
  const dotCost = FOOTER_ANOMALY_GAP + FOOTER_ANOMALY_DOT;
  const words = 30;
  const iconAt = iconWidth(textWidths);

  const withWords = chooseFooterLayout({ ...base, availableWidth: iconAt + dotCost + words, anomaly: true, anomalyTextWidth: words });
  assert.equal(withWords.showAnomalyText, true);
  assert.equal(withWords.showAnomalyMark, true);

  const textOnly = chooseFooterLayout({ ...base, availableWidth: iconAt + dotCost, anomaly: true, anomalyTextWidth: words });
  assert.equal(textOnly.showMeters, false);
  assert.equal(textOnly.showAnomalyText, false);
  assert.equal(textOnly.showAnomalyMark, true);

  const noRoomForDot = chooseFooterLayout({ ...base, availableWidth: iconAt + dotCost - 0.1, anomaly: true, anomalyTextWidth: words });
  assert.equal(noRoomForDot.showAnomalyText, false);
  assert.equal(noRoomForDot.showAnomalyMark, false);
  assert.equal(noRoomForDot.showIcons, true);
});
