/**
 * Accent roles for the Chinese-title panel, taken from the finalized dark
 * artboards. The plugin SDK exposes no `mode`/`appearance` field on
 * `PluginTheme` (`appearance` exists only on contributed themes), so the panel
 * reads dark/light from `surface0` with the same luminance rule the workspace
 * usage panel already uses. Neutral surfaces, text and status colors keep
 * coming from the Paseo theme.
 */

/** The only theme field this decision needs; `PluginTheme["colors"]` satisfies it. */
export interface PaletteSource {
  readonly surface0: string;
}

export interface PanelPalette {
  /** Accent text and marks: icon glyphs, radio dot, running notice. */
  readonly mark: string;
  /** Filled primary action background. */
  readonly action: string;
  /** Text on `action`; the artboard pairs #1c1335 with #b5a8ff. */
  readonly actionText: string;
  /** Icon tile fill and its 1px border. */
  readonly iconPlate: string;
  readonly iconBorder: string;
  /** Selected option tile fill and border. */
  readonly selectedPlate: string;
  readonly selectedEdge: string;
}

export function darkTheme(colors: PaletteSource): boolean {
  const hex = colors.surface0.replace("#", "");
  if (!/^[0-9a-f]{6}$/i.test(hex)) return true;
  const linear = (offset: number) => {
    const value = parseInt(hex.slice(offset, offset + 2), 16) / 255;
    return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  };
  const luminance = 0.2126 * linear(0) + 0.7152 * linear(2) + 0.0722 * linear(4);
  return (luminance + 0.05) / 0.05 < 1.05 / (luminance + 0.05);
}

export function panelPalette(colors: PaletteSource): PanelPalette {
  if (darkTheme(colors)) {
    return {
      mark: "#c1b7ff",
      action: "#b5a8ff",
      actionText: "#1c1335",
      iconPlate: "#232231",
      iconBorder: "#49455e",
      selectedPlate: "#252532",
      selectedEdge: "#8d80ca",
    };
  }
  return {
    // Darker purple; keeps text >=4.5:1 and edges >=3:1 on light neutral surfaces.
    mark: "#5b3fc4",
    action: "#5b3fc4",
    actionText: "#ffffff",
    iconPlate: "#efecf9",
    iconBorder: "#6b5abf",
    selectedPlate: "#efecf9",
    selectedEdge: "#5b3fc4",
  };
}
