import assert from "node:assert/strict";
import test from "node:test";

import {
  chooseFooterLayout,
  equalSlotsWidth,
  FOOTER_ANOMALY_DOT,
  FOOTER_ANOMALY_GAP,
  FOOTER_ICON_COST,
  FOOTER_METER_COST,
  FOOTER_ROW_GAP,
  FOOTER_ROW_GAP_TIGHT,
  FOOTER_SLOTS,
  textOnlyWidth,
} from "../shared/layout.ts";

const base = { compact: false, anomaly: false, anomalyTextWidth: 0 };
const even = [30, 30, 30];

test("equal-slot width uses the widest label per slot, not the sum", () => {
  const uneven = [26, 34, 30];
  const iconOnly = 20 + FOOTER_SLOTS * (34 + FOOTER_ICON_COST) + FOOTER_ROW_GAP * (FOOTER_SLOTS - 1);
  const withMeter = 20 + FOOTER_SLOTS * (34 + FOOTER_ICON_COST + FOOTER_METER_COST) + FOOTER_ROW_GAP * (FOOTER_SLOTS - 1);
  assert.equal(equalSlotsWidth(uneven, { icon: true, meter: false }), iconOnly);
  assert.equal(equalSlotsWidth(uneven, { icon: true, meter: true }), withMeter);
  // Not the sum-based content width.
  assert.notEqual(iconOnly, textOnlyWidth(uneven));
  assert.equal(FOOTER_SLOTS, 3);
});

test("wide sidebar uses three equal slots with meters, exact boundary included", () => {
  const threshold = equalSlotsWidth(even, { icon: true, meter: true });
  const at = chooseFooterLayout({ ...base, availableWidth: threshold, textWidths: even });
  assert.equal(at.mode, "equal");
  assert.equal(at.showMeters, true);
  assert.equal(at.showIcons, true);
  const below = chooseFooterLayout({ ...base, availableWidth: threshold - 0.1, textWidths: even });
  assert.equal(below.mode, "equal");
  assert.equal(below.showMeters, false);
  assert.equal(below.showIcons, true);
});

test("narrow-but-equal sidebar keeps three equal slots without meters, filling the row", () => {
  const threshold = equalSlotsWidth(even, { icon: true, meter: false });
  const at = chooseFooterLayout({ ...base, availableWidth: threshold, textWidths: even });
  assert.equal(at.mode, "equal");
  assert.equal(at.showMeters, false);
  assert.equal(at.showIcons, true);
  const below = chooseFooterLayout({ ...base, availableWidth: threshold - 0.1, textWidths: even });
  assert.equal(below.mode, "equal");
  assert.equal(below.showIcons, false);
});

test("compact layout never paints meters across equal slots", () => {
  const plan = chooseFooterLayout({ ...base, availableWidth: 400, compact: true, textWidths: even });
  assert.equal(plan.showMeters, false);
  assert.equal(plan.mode, "equal");
  assert.equal(plan.showIcons, true);
});

test("uneven labels only raise the equal threshold by the widest one", () => {
  const uneven = [26, 40, 30];
  const exact = equalSlotsWidth(uneven, { icon: true, meter: false });
  assert.equal(chooseFooterLayout({ ...base, availableWidth: exact, textWidths: uneven }).mode, "equal");
  const below = chooseFooterLayout({ ...base, availableWidth: exact - 0.1, textWidths: uneven });
  assert.equal(below.mode, "equal");
  assert.equal(below.showIcons, false);
});

test("content mode appears only when 3 x widest cannot fit, and is numbers-only", () => {
  const threshold = equalSlotsWidth(even, { icon: false, meter: false });
  const at = chooseFooterLayout({ ...base, availableWidth: threshold, textWidths: even });
  assert.equal(at.mode, "equal");
  assert.equal(at.showIcons, false);
  assert.equal(at.showMeters, false);

  // Even labels make both widths identical, so one step below is already tight.
  const below = chooseFooterLayout({ ...base, availableWidth: threshold - 0.1, textWidths: even });
  assert.equal(below.mode, "content");
  assert.equal(below.showMeters, false);
  assert.equal(below.showIcons, false);

  // A wider single reading must not bring decoration back.
  const uneven = [26, 40, 30];
  const unevenBelow = chooseFooterLayout({ ...base, availableWidth: equalSlotsWidth(uneven, { icon: false, meter: false }) - 0.1, textWidths: uneven });
  assert.equal(unevenBelow.mode, "content");
  assert.equal(unevenBelow.showIcons, false);
  assert.equal(unevenBelow.showMeters, false);
});

test("content mode squeezes its gap only below the normal numbers width", () => {
  // Uneven labels are what make content mode reachable: with equal labels the
  // numbers-only content width coincides with the three equal slots.
  const uneven = [26, 40, 30];
  assert.equal(textOnlyWidth(uneven), 134);
  assert.equal(textOnlyWidth(uneven, true), 124);
  assert.equal(FOOTER_ROW_GAP_TIGHT, 4);
  const atNormal = chooseFooterLayout({ ...base, availableWidth: 134, textWidths: uneven });
  assert.equal(atNormal.mode, "content");
  assert.equal(atNormal.tightGap, false);
  const squeezed = chooseFooterLayout({ ...base, availableWidth: 133.9, textWidths: uneven });
  assert.equal(squeezed.mode, "content");
  assert.equal(squeezed.tightGap, true);
});

test("an unmeasured first frame never paints a meter", () => {
  const plan = chooseFooterLayout({ availableWidth: null, compact: false, textWidths: [null, null, null], anomaly: false, anomalyTextWidth: 0 });
  assert.equal(plan.showMeters, false);
  assert.equal(plan.mode, "content");
});

test("an anomaly is sized into the equal-row budget: words, then dot, then nothing", () => {
  const words = 30;
  const slots = equalSlotsWidth(even, { icon: true, meter: false });
  const wordsPlan = chooseFooterLayout({ ...base, availableWidth: slots + FOOTER_ANOMALY_GAP + words, textWidths: even, anomaly: true, anomalyTextWidth: words });
  assert.equal(wordsPlan.mode, "equal");
  assert.equal(wordsPlan.showAnomalyText, true);
  assert.equal(wordsPlan.showAnomalyMark, true);

  const dotPlan = chooseFooterLayout({ ...base, availableWidth: slots + FOOTER_ANOMALY_GAP + FOOTER_ANOMALY_DOT, textWidths: even, anomaly: true, anomalyTextWidth: words });
  assert.equal(dotPlan.showAnomalyText, false);
  assert.equal(dotPlan.showAnomalyMark, true);

  const nonePlan = chooseFooterLayout({ ...base, availableWidth: slots + FOOTER_ANOMALY_GAP + FOOTER_ANOMALY_DOT - 0.1, textWidths: even, anomaly: true, anomalyTextWidth: words });
  assert.equal(nonePlan.showAnomalyText, false);
  assert.equal(nonePlan.showAnomalyMark, false);
  assert.equal(nonePlan.mode, "equal");
});

test("costs stay in sync with the rendered meter, icon and gaps", () => {
  assert.equal(FOOTER_ICON_COST, 16);
  assert.equal(FOOTER_METER_COST, 26);
  assert.equal(FOOTER_ROW_GAP, 9);
});
