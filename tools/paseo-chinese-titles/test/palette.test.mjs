import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { darkTheme, panelPalette } from "../shared/palette.ts";

/** WCAG 2.1 relative luminance and contrast ratio, computed here so the test pins the numbers. */
function luminance(hex) {
  const value = hex.replace("#", "");
  const channel = (offset) => {
    const c = parseInt(value.slice(offset, offset + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(0) + 0.7152 * channel(2) + 0.0722 * channel(4);
}
function contrast(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}
const round = (value) => Math.round(value * 100) / 100;

// Real surface triples from the Paseo 0.17.x web bundle: one light set, five dark sets.
const LIGHT = { surface0: "#ffffff", surface1: "#fafafa", surface2: "#f4f4f5" };
const DARKS = [
  { surface0: "#18181b", surface1: "#1f1f22", surface2: "#27272a" },
  { surface0: "#161820", surface1: "#1c1e27", surface2: "#252731" },
  { surface0: "#181B1A", surface1: "#1E2120", surface2: "#272A29" },
  { surface0: "#1f1f1e", surface1: "#262523", surface2: "#2f2d2b" },
  { surface0: "#282c34", surface1: "#2f333d", surface2: "#383c48" },
  { surface0: "#000000", surface1: "#0a0a0a", surface2: "#181818" },
];

test("dark detection follows the workspace-usage rule and falls back to dark", () => {
  assert.equal(darkTheme(LIGHT), false);
  for (const dark of DARKS) assert.equal(darkTheme(dark), true, dark.surface0);
  assert.equal(darkTheme({ surface0: "not-a-colour" }), true);
});

test("dark keeps the artboard purple verbatim", () => {
  const palette = panelPalette(DARKS[0]);
  assert.deepEqual(palette, {
    mark: "#c1b7ff",
    action: "#b5a8ff",
    actionText: "#1c1335",
    iconPlate: "#232231",
    iconBorder: "#49455e",
    selectedPlate: "#252532",
    selectedEdge: "#8d80ca",
  });
});

test("light uses a purple with readable text and control edges", () => {
  const palette = panelPalette(LIGHT);
  assert.equal(palette.mark, "#5b3fc4");
  assert.equal(palette.action, "#5b3fc4");
  assert.equal(palette.actionText, "#ffffff");
  for (const surface of Object.values(LIGHT)) {
    assert.ok(contrast(palette.mark, surface) >= 4.5, `mark on ${surface}`);
  }
  assert.ok(contrast(palette.actionText, palette.action) >= 4.5);
  assert.ok(contrast(palette.iconBorder, palette.iconPlate) >= 3);
  assert.ok(contrast(palette.selectedEdge, palette.selectedPlate) >= 3);
});

test("dark and light roles meet the contrast budget on every shipped surface", () => {
  const darkRatios = DARKS.map((surface) => ({
    surface,
    mark: round(contrast("#c1b7ff", surface.surface0)),
    mark2: round(contrast("#c1b7ff", surface.surface2)),
    dot: round(contrast("#b5a8ff", surface.surface2)),
    edge: round(contrast("#8d80ca", surface.surface2)),
  }));
  for (const row of darkRatios) {
    assert.ok(row.mark >= 4.5, `dark mark on surface0 ${row.surface.surface0}: ${row.mark}`);
    assert.ok(row.mark2 >= 4.5, `dark mark on surface2 ${row.surface.surface2}: ${row.mark2}`);
    assert.ok(row.dot >= 3, `dark dot on surface2 ${row.surface.surface2}: ${row.dot}`);
    assert.ok(row.edge >= 3, `dark selected edge on surface2 ${row.surface.surface2}: ${row.edge}`);
  }
  assert.equal(round(contrast("#1c1335", "#b5a8ff")), 8.38);
  assert.equal(round(contrast("#ffffff", "#5b3fc4")), 7.11);
  assert.equal(round(contrast("#5b3fc4", "#ffffff")), 7.11);
  assert.equal(round(contrast("#5b3fc4", "#f4f4f5")), 6.47);
});

test("the panel reads every accent role from the palette, never from theme.colors", async () => {
  // Source-level guard: the green came from `colors.accent`/`accentForeground`,
  // so a stray read of them would silently bring it back.
  const source = await readFile(new URL("../client/regenerate.tsx", import.meta.url), "utf8");
  assert.equal(source.match(/colors\.accent\b|colors\.accentForeground\b/g), null);
  assert.equal(source.match(/theme\.colors\.accent\b/g), null);
  assert.equal(source.match(/import \{ panelPalette \} from "\.\.\/shared\/palette";/g)?.length, 1);
  const uses = source.match(/accent\.(mark|action|actionText|iconPlate|iconBorder|selectedPlate|selectedEdge)\b/g) ?? [];
  assert.ok(uses.length >= 7, `expected every role in use, saw ${uses.length}`);
  // Neutral surfaces, text and status colors still come from the Paseo theme.
  for (const role of ["surface0", "surface1", "border", "foreground", "foregroundMuted", "statusSuccess", "statusWarning", "statusDanger"]) {
    assert.ok(source.includes(`colors.${role}`), `${role} should stay a theme read`);
  }
});
