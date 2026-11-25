/**
 * Footer row fitting for the sidebar item.
 *
 * The desktop sidebar can be dragged down to its minimum width (200 DP in
 * Paseo 0.17.4) while still reporting a non-compact layout. The three host
 * readings must stay identifiable there: CPU, memory and disk each keep their
 * icon and their full percentage. To make that fit, the row tightens its own
 * padding, icon size and icon/label gap before it gives anything up, and only
 * as a last resort stacks the icon above the number inside the same column.
 *
 * Every width in this module is an outer (onLayout frame) width in DP/CSS
 * pixels. `frameInset(paddingX)` is the horizontal chrome (padding + border).
 *
 * Arrangements, in decreasing width:
 * 1. "row"       icon + percentage + meter, three equal columns
 * 2. "row"       icon + percentage, three equal columns
 * 3. "row"       compact padding/icon, three equal columns
 * 4. "stacked"   icon above percentage, three equal columns
 * 5. "content"   percentages only, content-sized (physical floor)
 *
 * Fitting uses the *widest* of the three labels for every column, since equal
 * columns are all sized by the largest.
 */

export const FOOTER_SLOTS = 3;
export const FOOTER_BORDER_X = 2; // borderWidth 1 on both sides
export const FOOTER_PAD_X = 9;
export const FOOTER_PAD_X_TIGHT = 4;
export const FOOTER_COL_GAP = 9;
export const FOOTER_COL_GAP_TIGHT = 2;
export const FOOTER_ICON_SIZE = 12;
export const FOOTER_ICON_SIZE_TIGHT = 10;
export const FOOTER_ICON_GAP = 4;
export const FOOTER_ICON_GAP_TIGHT = 2;
export const FOOTER_METER_COST = 26; // 4 px gap + 22 px meter
export const FOOTER_ANOMALY_GAP = 9;
export const FOOTER_ANOMALY_DOT = 8;
/** Two-line down/up rate group; the arrow, unit and digits need this much. */
export const FOOTER_NETWORK_WIDTH = 92;
export const FOOTER_NETWORK_GAP = 10;

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
  /** Equal columns spanning the row, or a content-sized numbers-only row. */
  mode: "row" | "stacked" | "content";
  showMeters: boolean;
  /** Icons stay on every tier except the physical-floor content row. */
  showIcons: boolean;
  stacked: boolean;
  paddingX: number;
  columnGap: number;
  iconSize: number;
  iconGap: number;
  /** Content mode only: squeeze the inter-reading gap. */
  tightGap: boolean;
  /** Host-wide ↓/↑ rates are shown beside the three resource columns. */
  showNetwork: boolean;
  /** The words `旧样本` / `读取失败`; falls back to the dot when too narrow. */
  showAnomalyText: boolean;
  /** Status dot. Hidden only when even a dot would push a number out. */
  showAnomalyMark: boolean;
}

interface RowStyle {
  paddingX: number;
  columnGap: number;
  iconSize: number;
  iconGap: number;
  meter: boolean;
  stacked: boolean;
}

const NORMAL: RowStyle = {
  paddingX: FOOTER_PAD_X,
  columnGap: FOOTER_COL_GAP,
  iconSize: FOOTER_ICON_SIZE,
  iconGap: FOOTER_ICON_GAP,
  meter: true,
  stacked: false,
};
const NO_METER: RowStyle = { ...NORMAL, meter: false };
const TIGHT: RowStyle = {
  paddingX: FOOTER_PAD_X_TIGHT,
  columnGap: FOOTER_COL_GAP_TIGHT,
  iconSize: FOOTER_ICON_SIZE_TIGHT,
  iconGap: FOOTER_ICON_GAP_TIGHT,
  meter: false,
  stacked: false,
};
const STACKED: RowStyle = { ...TIGHT, stacked: true };

const ROW_STYLES = [NORMAL, NO_METER, TIGHT, STACKED];

function sumText(textWidths: readonly (number | null)[]): number {
  return textWidths.reduce<number>((total, width) => total + (width ?? 0), 0);
}

function maxText(textWidths: readonly (number | null)[]): number {
  return textWidths.reduce<number>((widest, width) => Math.max(widest, width ?? 0), 0);
}

export function frameInset(paddingX: number): number {
  return paddingX * 2 + FOOTER_BORDER_X;
}

/** Width of one equal column for the current style. */
export function columnWidth(textWidths: readonly (number | null)[], style: RowStyle): number {
  const widest = maxText(textWidths);
  if (style.stacked) return Math.max(widest, style.iconSize);
  return widest + style.iconSize + style.iconGap + (style.meter ? FOOTER_METER_COST : 0);
}

/** Outer width for the three equal columns of a given style. */
export function rowWidth(textWidths: readonly (number | null)[], style: RowStyle): number {
  return frameInset(style.paddingX) + FOOTER_SLOTS * columnWidth(textWidths, style) + style.columnGap * (FOOTER_SLOTS - 1);
}

/** Outer width needed for the percentages alone. */
export function textOnlyWidth(textWidths: readonly (number | null)[], tight = false): number {
  const gap = tight ? FOOTER_COL_GAP_TIGHT : FOOTER_COL_GAP;
  return frameInset(FOOTER_PAD_X_TIGHT) + sumText(textWidths) + gap * Math.max(0, textWidths.length - 1);
}

/** Exposed for tests and callers that need the tier thresholds. */
export const FOOTER_STYLES = ROW_STYLES;

type AnomalyEdge = "text" | "dot" | "none";

/**
 * Cost of the anomaly badge when it sits after the three columns: it adds one
 * more gap plus its own width, so the budget must include both.
 */
function anomalyCost(anomaly: boolean, edge: AnomalyEdge, textWidth: number, columnGap: number): number {
  if (!anomaly || edge === "none") return 0;
  return columnGap + FOOTER_ANOMALY_GAP + (edge === "text" ? textWidth : FOOTER_ANOMALY_DOT);
}

function anomalyEdgeFor(anomaly: boolean, remaining: number, textWidth: number, columnGap: number): AnomalyEdge {
  if (!anomaly) return "none";
  if (remaining >= columnGap + FOOTER_ANOMALY_GAP + textWidth) return "text";
  if (remaining >= columnGap + FOOTER_ANOMALY_GAP + FOOTER_ANOMALY_DOT) return "dot";
  return "none";
}

export function chooseFooterLayout(input: FooterLayoutInput): FooterLayout {
  const { availableWidth, compact, textWidths, anomaly, anomalyTextWidth } = input;
  const measured =
    availableWidth !== null && textWidths.length === FOOTER_SLOTS && textWidths.every((width) => width !== null);
  if (!measured) {
    // Never paint a meter on the first frame, but keep the icons and columns.
    return {
      mode: "row",
      showMeters: false,
      showIcons: true,
      stacked: false,
      paddingX: FOOTER_PAD_X,
      columnGap: FOOTER_COL_GAP,
      iconSize: FOOTER_ICON_SIZE,
      iconGap: FOOTER_ICON_GAP,
      tightGap: false,
      // Unmeasured rows are assumed narrow: the rate group joins only once the
      // real width confirms room for the three columns plus it.
      showNetwork: false,
      showAnomalyText: anomaly,
      showAnomalyMark: anomaly,
    };
  }

  const need = availableWidth as number;
  const tiers = compact ? ROW_STYLES.filter((style) => !style.meter) : ROW_STYLES;
  for (const style of tiers) {
    const base = rowWidth(textWidths, style);
    // Rates ride beside the widest tier only, and only after the three columns
    // and any anomaly badge have their full share. Otherwise the columns win.
    const candidates = style.meter
      ? [
          { base: base + FOOTER_NETWORK_GAP + FOOTER_NETWORK_WIDTH, network: true },
          { base, network: false },
        ]
      : [{ base, network: false }];
    for (const candidate of candidates) {
      if (need < candidate.base) continue;
      const edge = anomalyEdgeFor(anomaly, need - candidate.base, anomalyTextWidth, style.columnGap);
      // The rate group is optional decoration: it may not eat into the anomaly
      // badge's room. The three readings and their number always rank first.
      if (candidate.network && anomaly && need < candidate.base + style.columnGap + FOOTER_ANOMALY_GAP + anomalyTextWidth) {
        continue;
      }
      if (need >= candidate.base + anomalyCost(anomaly, edge, anomalyTextWidth, style.columnGap)) {
        return {
          mode: style.stacked ? "stacked" : "row",
          showMeters: style.meter,
          showIcons: true,
          stacked: style.stacked,
          paddingX: style.paddingX,
          columnGap: style.columnGap,
          iconSize: style.iconSize,
          iconGap: style.iconGap,
          tightGap: false,
          showNetwork: candidate.network,
          showAnomalyText: edge === "text",
          showAnomalyMark: edge !== "none",
        };
      }
    }
  }

  // Physical floor: not even three icon-above-number columns fit. Keep only the
  // numbers, content-sized, so nothing is clipped or ellipsized.
  const normal = textOnlyWidth(textWidths);
  const tightGap = need < normal;
  const base = tightGap ? textOnlyWidth(textWidths, true) : normal;
  const edge = anomalyEdgeFor(anomaly, need - base, anomalyTextWidth, FOOTER_COL_GAP_TIGHT);
  return {
    mode: "content",
    showMeters: false,
    showIcons: false,
    stacked: false,
    paddingX: FOOTER_PAD_X_TIGHT,
    columnGap: tightGap ? FOOTER_COL_GAP_TIGHT : FOOTER_COL_GAP,
    iconSize: FOOTER_ICON_SIZE_TIGHT,
    iconGap: FOOTER_ICON_GAP_TIGHT,
    tightGap,
    showNetwork: false,
    showAnomalyText: edge === "text",
    showAnomalyMark: edge !== "none",
  };
}
