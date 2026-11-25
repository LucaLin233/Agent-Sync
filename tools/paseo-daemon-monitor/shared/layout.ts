/**
 * Footer row geometry for the daemon-monitor sidebar item.
 *
 * One 44 DP line. The row measures its own outer width W and always reserves a
 * right-hand tail track of clamp(W - 368, 0, 112) DP. Because the track grows
 * at the same rate as W until it caps, the three columns keep exactly the same
 * width while the tail content appears (416 DP) and is replaced by rates
 * (480 DP): nothing in the first three groups jumps at either boundary.
 *
 * The rest of the row is split into three equal columns. Each column keeps its
 * leftmost icon and a non-shrinking tabular number slot; the meter takes
 * whatever width is left over, so it lengthens with the sidebar instead of
 * staying a fixed 22 DP stub. It is only drawn when that leftover is at least
 * FOOTER_METER_MIN, so a narrow row gives the numbers all the space first.
 *
 * Tiers, wide to narrow:
 * 1. Icon + full number + meter (meter >= 14 DP of leftover width).
 * 2. Icon + full number, meter retracted (design: 248 DP container).
 * 3. Too narrow for one line: icon above the number.
 * 4. Too narrow even for that: the three numbers alone, never clipped.
 *
 * All widths are outer (onLayout frame) DP/CSS pixels.
 */

export const FOOTER_HEIGHT = 44;
export const FOOTER_PAD_X = 8;
export const FOOTER_BORDER_X = 2;
export const FOOTER_SLOTS = 3;

/** Tail track: clamp(W - 368, 0, 112) DP, reserved whether or not it has text. */
export const FOOTER_TAIL_ANCHOR = 368;
export const FOOTER_TAIL_MAX = 112;
/** Sample time joins the tail from this outer width (design container query). */
export const FOOTER_TIME_MIN_WIDTH = 416;
/** Rates replace the sample time from this outer width (design container query). */
export const FOOTER_NETWORK_MIN_WIDTH = 480;
/** Below this the design hides the meter regardless of leftover width. */
export const FOOTER_METER_MIN_WIDTH = 248;
/** Minimum meter length worth drawing; the number always comes first. */
export const FOOTER_METER_MIN = 14;

export const FOOTER_ICON_SIZE = 12;
export const FOOTER_ICON_SIZE_STACKED = 11;
export const FOOTER_ICON_GAP = 4;
export const FOOTER_COL_PAD_X = 5;

/** Conservative first-frame width for `100%` at 11 px bold tabular digits. */
export const FOOTER_TEXT_FALLBACK = 40;

export type FooterMode = "row" | "stacked" | "content";
export type FooterTail = "none" | "time" | "network";

export interface FooterPlanInput {
  /** Outer width from onLayout, or null before the first pass. */
  width: number | null;
  /** Intrinsic widths of the three percentage labels (null renders an em dash). */
  textWidths: readonly (number | null)[];
  /** The host exposes network counters and the last sample carries a rate. */
  networkAvailable: boolean;
  /** The host-scoped "show network in footer" switch. */
  showNetworkSetting: boolean;
  /** The host reports its narrow/compact layout; meters stay retracted there. */
  compact: boolean;
}

export interface FooterPlan {
  /** False before the first onLayout; columns then share the row with flex. */
  measured: boolean;
  mode: FooterMode;
  showIcons: boolean;
  showMeters: boolean;
  /** Drawn meter length in DP; 0 when hidden. */
  meterWidth: number;
  stacked: boolean;
  /** Tail content is visible (the track is reserved regardless). */
  showTail: boolean;
  tail: FooterTail;
  /** Reserved tail track width in DP. */
  tailWidth: number;
  /** One equal column's outer width in DP. */
  columnWidth: number;
  iconSize: number;
  iconGap: number;
  columnPadX: number;
}

export function tailBudget(width: number): number {
  return Math.min(FOOTER_TAIL_MAX, Math.max(0, width - FOOTER_TAIL_ANCHOR));
}

function labelWidths(textWidths: readonly (number | null)[]): number[] {
  return Array.from({ length: FOOTER_SLOTS }, (_, index) => textWidths[index] ?? FOOTER_TEXT_FALLBACK);
}

/** Inner width is outer minus chrome and the reserved tail track. */
export function columnWidthFor(width: number): number {
  return Math.max(0, width - FOOTER_PAD_X * 2 - FOOTER_BORDER_X - tailBudget(width)) / FOOTER_SLOTS;
}

export function chooseFooterPlan(input: FooterPlanInput): FooterPlan {
  const measured = input.width !== null;
  const width = input.width ?? 0;
  const labels = labelWidths(input.textWidths);
  const widest = Math.max(...labels);

  const tailWidth = measured ? tailBudget(width) : 0;
  const columnWidth = measured ? columnWidthFor(width) : 0;
  const usable = Math.max(0, columnWidth - FOOTER_COL_PAD_X * 2);

  const rowNeeds = FOOTER_ICON_SIZE + FOOTER_ICON_GAP + widest;
  // A meter adds one more gap before it, so it only gets what remains after that.
  const meterRoom = usable - rowNeeds - FOOTER_ICON_GAP;
  const stackedNeeds = Math.max(widest, FOOTER_ICON_SIZE_STACKED);

  let mode: FooterMode = "row";
  let showIcons = true;
  let showMeters = false;
  let stacked = false;
  let iconSize = FOOTER_ICON_SIZE;
  let iconGap = FOOTER_ICON_GAP;

  if (!measured) {
    // First frame: icons and columns only, never a meter or tail text yet.
  } else if (!input.compact && width >= FOOTER_METER_MIN_WIDTH && meterRoom >= FOOTER_METER_MIN) {
    showMeters = true;
  } else if (usable >= rowNeeds) {
    // Icons plus the full number on one line; the meter is retracted.
  } else if (usable >= stackedNeeds) {
    mode = "stacked";
    stacked = true;
    iconSize = FOOTER_ICON_SIZE_STACKED;
    iconGap = 1;
  } else {
    mode = "content";
    showIcons = false;
    iconSize = 0;
    iconGap = 0;
  }

  const showTail = measured && width >= FOOTER_TIME_MIN_WIDTH && tailWidth > 0;
  const tail: FooterTail = !showTail
    ? "none"
    : input.networkAvailable && input.showNetworkSetting && width >= FOOTER_NETWORK_MIN_WIDTH
      ? "network"
      : "time";

  return {
    measured,
    mode,
    showIcons,
    showMeters,
    meterWidth: showMeters ? meterRoom : 0,
    stacked,
    showTail,
    tail,
    tailWidth,
    columnWidth,
    iconSize,
    iconGap,
    columnPadX: FOOTER_COL_PAD_X,
  };
}
