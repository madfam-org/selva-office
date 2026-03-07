/** A 2D grid of pixel tokens. null = transparent. */
export type PixelGrid = (string | null)[][];

/** A sprite template with dimensions and pixel data. */
export interface SpriteTemplate {
  width: number;
  height: number;
  pixels: PixelGrid;
}

/** Re-export palette and color resolver */
export {
  resolveColorMap,
  resolveRoleColorMap,
  resolveEnvironmentColorMap,
  resolveThemeColorMap,
  darken,
  lighten,
  saturate,
  hueShift,
  tint,
} from './resolve-colors';

/** Re-export palette presets */
export {
  PALETTE_PRESETS,
  type PalettePreset,
  type PalettePresetName,
} from './palette-presets';
