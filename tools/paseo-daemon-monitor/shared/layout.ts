/**
 * Footer row fitting for the sidebar item.
 *
 * The desktop sidebar can be dragged arbitrarily narrow while still reporting a
 * non-compact layout. RN text neither shrinks nor ellipsizes usefully at 11 px,
 * so the row sheds decoration in a fixed order as its measured width shrinks:
 * meters, then icons, then the tighter reading gap, and finally the anomaly
 * dot. Every width below is an outer (onLayout frame) width in DP/CSS pixels;
 * `FOOTER_INSET_X` is subtracted once to get the usable content width.
 */

export const FOOTER_INSET_X = 20; // paddingHorizontal 9 + borderWidth 1, both sides
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
  showMeters: boolean;
  showIcons: boolean;
  /** Squeeze the inter-reading gap to keep all three percentages intact. */
  tightGap: boolean;
  /** The words `旧样本` / `读取失败`; falls back to the dot when too narrow. */
  showAnomalyText: boolean;
  /** Status dot. Hidden when even the dot would push a number out of the row. */
  showAnomalyMark: boolean;
}

function sumText(textWidths: readonly (number | null)[]): number {
  return textWidths.reduce<number>((total, width) => total + (width ?? 0), 0);
}

function readingsWidth(textWidths: readonly (number | null)[], gap: number, perReading: number): number {
  const count = textWidths.length;
  return sumText(textWidths) + gap * Math.max(0, count - 1) + perReading * count;
}

/** Outer width needed for the percentages alone (no padding subtracted). */
export function textOnlyWidth(textWidths: readonly (number | null)[], tight = false): number {
  return FOOTER_INSET_X + readingsWidth(textWidths, tight ? FOOTER_ROW_GAP_TIGHT : FOOTER_ROW_GAP, 0);
}

/** Outer width with icons but no meters. */
export function iconWidth(textWidths: readonly (number | null)[]): number {
  return FOOTER_INSET_X + readingsWidth(textWidths, FOOTER_ROW_GAP, FOOTER_ICON_COST);
}

/** Outer width with icons and meters. */
export function meterWidth(textWidths: readonly (number | null)[]): number {
  return FOOTER_INSET_X + readingsWidth(textWidths, FOOTER_ROW_GAP, FOOTER_ICON_COST + FOOTER_METER_COST);
}

export function chooseFooterLayout(input: FooterLayoutInput): FooterLayout {
  const { availableWidth, compact, textWidths, anomaly, anomalyTextWidth } = input;
  const measured =
    availableWidth !== null && textWidths.length > 0 && textWidths.every((width) => width !== null);
  if (!measured) {
    // Never paint a meter on the first frame: an unmeasured row can be at any width.
    return {
      showMeters: false,
      showIcons: true,
      tightGap: false,
      showAnomalyText: anomaly,
      showAnomalyMark: anomaly,
    };
  }

  const need = availableWidth as number;
  const meters = meterWidth(textWidths);
  const icons = iconWidth(textWidths);
  const normal = textOnlyWidth(textWidths);
  const tight = textOnlyWidth(textWidths, true);

  let showMeters = false;
  let showIcons = false;
  let tightGap = false;
  let base: number;
  if (!compact && need >= meters) {
    showMeters = true;
    showIcons = true;
    base = meters;
  } else if (need >= icons) {
    showIcons = true;
    base = icons;
  } else if (need >= normal) {
    base = normal;
  } else {
    tightGap = true;
    base = tight;
  }

  if (!anomaly) {
    return { showMeters, showIcons, tightGap, showAnomalyText: false, showAnomalyMark: false };
  }
  if (need >= base + FOOTER_ANOMALY_GAP + anomalyTextWidth) {
    return { showMeters, showIcons, tightGap, showAnomalyText: true, showAnomalyMark: true };
  }
  const showAnomalyMark = need >= base + FOOTER_ANOMALY_GAP + FOOTER_ANOMALY_DOT;
  return { showMeters, showIcons, tightGap, showAnomalyText: false, showAnomalyMark };
}
