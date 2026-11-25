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
/**
 * Compact (phone) footer: the three resource groups share the row with a
 * fourth right-hand group holding ↓ and ↑ on two stacked lines. Its width is
 * the widest rate label plus this separator/padding allowance. There is no
 * 368/416/480 anchor on this layout; the tail exists only while a rate is
 * actually available and the switch is on, so its space returns to the three
 * columns otherwise.
 */
export const FOOTER_COMPACT_RATE_FALLBACK = 40;
export const FOOTER_COMPACT_TAIL_PAD = 9;
/** Desktop keeps the clock above this font scale: two inline rates no longer fit. */
export const FOOTER_NETWORK_MAX_FONT_SCALE = 1.4;

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
  /** The host reports its narrow/compact layout (phone / narrow window). */
  compact: boolean;
  /**
   * Optional override for the compact rate budget, already in DP. The default
   * derives it from the fixed 9 px label and the user's font scale, so the
   * budget never depends on the digits currently drawn.
   */
  rateTextWidth?: number | null;
  /** User font scale, used only for the compact rate fallback before measuring. */
  fontScale?: number;
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
  /** Compact tail stacks ↓ over ↑; desktop keeps them inline. */
  tailStacked: boolean;
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

/** Equal column width for the outer row minus chrome and a given tail. */
function columnWidthWithout(width: number, tailWidth: number): number {
  return Math.max(0, width - FOOTER_PAD_X * 2 - FOOTER_BORDER_X - tailWidth) / FOOTER_SLOTS;
}

export function chooseFooterPlan(input: FooterPlanInput): FooterPlan {
  const measured = input.width !== null;
  const width = input.width ?? 0;
  const labels = labelWidths(input.textWidths);
  const widest = Math.max(...labels);

  const rowNeeds = FOOTER_ICON_SIZE + FOOTER_ICON_GAP + widest;
  const stackedNeeds = Math.max(widest, FOOTER_ICON_SIZE_STACKED);
  // A meter adds one more gap before it, so it only gets what remains after that.
  const meterRoomFor = (column: number) => Math.max(0, column - FOOTER_COL_PAD_X * 2) - rowNeeds - FOOTER_ICON_GAP;
  const usableFor = (column: number) => Math.max(0, column - FOOTER_COL_PAD_X * 2);

  // One budget for the widest label the short formatter can print (e.g.
  // `↓51200M`) at the user's font scale. Deriving it from the scale instead of
  // the live digits means a reading changing from `9.1K` to `2.4M` cannot
  // re-flow the three columns, and it can never get stuck on a past maximum.
  const rateReserve = Math.ceil(input.rateTextWidth ?? FOOTER_COMPACT_RATE_FALLBACK * (input.fontScale ?? 1));
  const networkWanted = input.networkAvailable && input.showNetworkSetting;

  let tailWidth = 0;
  let tail: FooterTail = "none";

  if (measured && input.compact) {
    // Four zones: three resource groups plus a two-line rate group. It only
    // takes space when there is a real rate to show, and it is dropped if the
    // three groups would no longer fit icon + full number side by side.
    if (networkWanted) {
      const candidate = rateReserve + FOOTER_COMPACT_TAIL_PAD;
      const column = columnWidthWithout(width, candidate);
      if (usableFor(column) >= rowNeeds) {
        tailWidth = candidate;
        tail = "network";
      }
    }
  } else if (measured) {
    // Desktop keeps the fixed anchor/cap so 416 and 480 never re-flow the row.
    tailWidth = tailBudget(width);
    if (width >= FOOTER_TIME_MIN_WIDTH && tailWidth > 0) {
      // Two rates sit side by side in this tail; past the documented font
      // scale they no longer fit, so the clock stays exactly as before.
      tail =
        networkWanted &&
        width >= FOOTER_NETWORK_MIN_WIDTH &&
        (input.fontScale ?? 1) <= FOOTER_NETWORK_MAX_FONT_SCALE
          ? "network"
          : "time";
    }
  }

  const columnWidth = measured ? columnWidthWithout(width, tailWidth) : 0;
  const usable = usableFor(columnWidth);
  const meterRoom = meterRoomFor(columnWidth);
  const meterEligible =
    measured && meterRoom >= FOOTER_METER_MIN && (input.compact || width >= FOOTER_METER_MIN_WIDTH);

  let mode: FooterMode = "row";
  let showIcons = true;
  let showMeters = false;
  let stacked = false;
  let iconSize = FOOTER_ICON_SIZE;
  let iconGap = FOOTER_ICON_GAP;

  if (!measured) {
    // First frame: icons and columns only, never a meter or tail text yet.
  } else if (meterEligible) {
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

  const showTail = measured && tailWidth > 0 && tail !== "none";

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
    tailStacked: input.compact,
  };
}
