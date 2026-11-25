/**
 * Footer row fitting for the sidebar item.
 *
 * The desktop sidebar can be dragged arbitrarily narrow while still reporting a
 * non-compact layout. RN text neither shrinks nor ellipsizes usefully at 11 px,
 * so the row sheds decoration as its measured width shrinks. Every width here
 * is an outer (onLayout frame) width in DP/CSS pixels; `FOOTER_INSET_X` is
 * subtracted once to get the usable content width.
 *
 * Two arrangements exist:
 * - "equal": three equal-width slots spanning the inner width, each centring
 *   its icon, percentage and optional meter. Fitting uses the *widest* of the
 *   three labels, not their sum, because every slot is sized by the largest.
 * - "content": numbers only, content-sized, used only when three slots of the
 *   widest label genuinely cannot fit. No icons or meters here either: adding
 *   decoration back for one wider reading is what squeezed the numbers before.
 */

export const FOOTER_INSET_X = 20; // paddingHorizontal 9 + borderWidth 1, both sides
export const FOOTER_SLOTS = 3;
export const FOOTER_ROW_GAP = 9;
export const FOOTER_ROW_GAP_TIGHT = 4;
export const FOOTER_ICON_COST = 16; // 12 px icon + 4 px gap
export const FOOTER_METER_COST = 26; // 4 px gap + 22 px meter
export const FOOTER_ANOMALY_GAP = 9;
export const FOOTER_ANOMALY_DOT = 8;

export interface FooterLayoutInput {
  /** Outer width of the footer row (onLayout frame width), or null before the first pass. */
  availableWidth: number | null;
  /** The host reported its narrow/compact layout. */
  compact: boolean;
  /** Intrinsic widths of the three percentage labels; null until measured. */
  textWidths: readonly (number | null)[];
  /** An anomaly badge is currently displayed. */
  anomaly: boolean;
  /** Estimated width of the anomaly label at the current font scale. */
  anomalyTextWidth: number;
}

export interface FooterLayout {
  /** Equal slots spanning the row, or a content-sized numbers-only row. */
  mode: "equal" | "content";
  showMeters: boolean;
  showIcons: boolean;
  /** Content mode only: squeeze the inter-reading gap to keep all three percentages. */
  tightGap: boolean;
  /** The words `旧样本` / `读取失败`; falls back to the dot when too narrow. */
  showAnomalyText: boolean;
  /** Status dot. Hidden when even the dot would push a number out of the row. */
  showAnomalyMark: boolean;
}

function sumText(textWidths: readonly (number | null)[]): number {
  return textWidths.reduce<number>((total, width) => total + (width ?? 0), 0);
}

function maxText(textWidths: readonly (number | null)[]): number {
  return textWidths.reduce<number>((widest, width) => Math.max(widest, width ?? 0), 0);
}

/** Outer width needed for the percentages alone (no padding subtracted). */
export function textOnlyWidth(textWidths: readonly (number | null)[], tight = false): number {
  const gap = tight ? FOOTER_ROW_GAP_TIGHT : FOOTER_ROW_GAP;
  return FOOTER_INSET_X + sumText(textWidths) + gap * Math.max(0, textWidths.length - 1);
}

/**
 * Outer width for three equal slots. Each slot must hold the widest label, so
 * this is 3 × (widest + decoration), not the sum of the three labels.
 */
export function equalSlotsWidth(
  textWidths: readonly (number | null)[],
  options: { icon: boolean; meter: boolean },
): number {
  const slot = maxText(textWidths) + (options.icon ? FOOTER_ICON_COST : 0) + (options.meter ? FOOTER_METER_COST : 0);
  return FOOTER_INSET_X + FOOTER_SLOTS * slot + FOOTER_ROW_GAP * (FOOTER_SLOTS - 1);
}

type AnomalyEdge = "text" | "dot" | "none";

function anomalyCost(anomaly: boolean, edge: AnomalyEdge, textWidth: number): number {
  if (!anomaly || edge === "none") return 0;
  return FOOTER_ANOMALY_GAP + (edge === "text" ? textWidth : FOOTER_ANOMALY_DOT);
}

function anomalyEdgeFor(anomaly: boolean, remaining: number, textWidth: number): AnomalyEdge {
  if (!anomaly) return "none";
  if (remaining >= FOOTER_ANOMALY_GAP + textWidth) return "text";
  if (remaining >= FOOTER_ANOMALY_GAP + FOOTER_ANOMALY_DOT) return "dot";
  return "none";
}

export function chooseFooterLayout(input: FooterLayoutInput): FooterLayout {
  const { availableWidth, compact, textWidths, anomaly, anomalyTextWidth } = input;
  const measured =
    availableWidth !== null && textWidths.length === FOOTER_SLOTS && textWidths.every((width) => width !== null);
  if (!measured) {
    // Never paint a meter on the first frame: an unmeasured row can be at any width.
    return {
      mode: "content",
      showMeters: false,
      showIcons: true,
      tightGap: false,
      showAnomalyText: anomaly,
      showAnomalyMark: anomaly,
    };
  }

  const need = availableWidth as number;
  const equalOptions = compact
    ? [
        { icon: true, meter: false },
        { icon: false, meter: false },
      ]
    : [
        { icon: true, meter: true },
        { icon: true, meter: false },
        { icon: false, meter: false },
      ];
  for (const options of equalOptions) {
    const base = equalSlotsWidth(textWidths, options);
    const edge = anomalyEdgeFor(anomaly, need - base, anomalyTextWidth);
    if (need >= base + anomalyCost(anomaly, edge, anomalyTextWidth)) {
      return {
        mode: "equal",
        showMeters: options.meter,
        showIcons: options.icon,
        tightGap: false,
        showAnomalyText: edge === "text",
        showAnomalyMark: edge !== "none",
      };
    }
  }

  const normal = textOnlyWidth(textWidths);
  const tightGap = need < normal;
  const base = tightGap ? textOnlyWidth(textWidths, true) : normal;
  const edge = anomalyEdgeFor(anomaly, need - base, anomalyTextWidth);
  return {
    mode: "content",
    showMeters: false,
    showIcons: false,
    tightGap,
    showAnomalyText: edge === "text",
    showAnomalyMark: edge !== "none",
  };
}
