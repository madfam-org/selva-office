import type { AvatarConfig } from '../avatar';
import { SKIN_TONES, HAIR_COLORS, OUTFIT_COLORS } from '../avatar';
import { PALETTE_PRESETS, type PalettePreset } from './palette-presets';

// ── Internal helpers ────────────────────────────────

function parseHex(hex: string): [number, number, number] {
  return [
    parseInt(hex.slice(1, 3), 16),
    parseInt(hex.slice(3, 5), 16),
    parseInt(hex.slice(5, 7), 16),
  ];
}

function toHex(r: number, g: number, b: number): string {
  const clamp = (v: number) => Math.max(0, Math.min(255, Math.round(v)));
  return `#${clamp(r).toString(16).padStart(2, '0')}${clamp(g).toString(16).padStart(2, '0')}${clamp(b).toString(16).padStart(2, '0')}`;
}

function rgbToHsl(r: number, g: number, b: number): [number, number, number] {
  r /= 255; g /= 255; b /= 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  const l = (max + min) / 2;
  if (max === min) return [0, 0, l];
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  let h = 0;
  if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
  else if (max === g) h = ((b - r) / d + 2) / 6;
  else h = ((r - g) / d + 4) / 6;
  return [h, s, l];
}

function hslToRgb(h: number, s: number, l: number): [number, number, number] {
  if (s === 0) {
    const v = Math.round(l * 255);
    return [v, v, v];
  }
  const hue2rgb = (p: number, q: number, t: number) => {
    if (t < 0) t += 1;
    if (t > 1) t -= 1;
    if (t < 1 / 6) return p + (q - p) * 6 * t;
    if (t < 1 / 2) return q;
    if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
    return p;
  };
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
  const p = 2 * l - q;
  return [
    Math.round(hue2rgb(p, q, h + 1 / 3) * 255),
    Math.round(hue2rgb(p, q, h) * 255),
    Math.round(hue2rgb(p, q, h - 1 / 3) * 255),
  ];
}

// ── Public color utilities ──────────────────────────

/**
 * Darken a hex color by a factor (0 = same, 1 = black).
 */
export function darken(hex: string, factor: number): string {
  const [r, g, b] = parseHex(hex);
  return toHex(r * (1 - factor), g * (1 - factor), b * (1 - factor));
}

/**
 * Lighten a hex color by a factor (0 = same, 1 = white).
 */
export function lighten(hex: string, factor: number): string {
  const [r, g, b] = parseHex(hex);
  return toHex(r + (255 - r) * factor, g + (255 - g) * factor, b + (255 - b) * factor);
}

/**
 * Adjust saturation of a hex color by a factor.
 * factor > 1 = more saturated, factor < 1 = less saturated, 0 = grayscale.
 */
export function saturate(hex: string, factor: number): string {
  const [r, g, b] = parseHex(hex);
  const [h, s, l] = rgbToHsl(r, g, b);
  const [nr, ng, nb] = hslToRgb(h, Math.min(1, s * factor), l);
  return toHex(nr, ng, nb);
}

/**
 * Shift the hue of a hex color by the given degrees (0-360).
 */
export function hueShift(hex: string, degrees: number): string {
  const [r, g, b] = parseHex(hex);
  const [h, s, l] = rgbToHsl(r, g, b);
  const newH = ((h * 360 + degrees) % 360) / 360;
  const [nr, ng, nb] = hslToRgb(newH < 0 ? newH + 1 : newH, s, l);
  return toHex(nr, ng, nb);
}

/**
 * Tint a hex color toward a target tint color by the given factor (0 = no change, 1 = full tint).
 */
export function tint(hex: string, tintHex: string, factor: number): string {
  const [r, g, b] = parseHex(hex);
  const [tr, tg, tb] = parseHex(tintHex);
  return toHex(
    r + (tr - r) * factor,
    g + (tg - g) * factor,
    b + (tb - b) * factor,
  );
}

/**
 * Resolve palette tokens to actual hex colors based on avatar config.
 */
export function resolveColorMap(config: AvatarConfig): Record<string, string> {
  const skin = SKIN_TONES[config.skinTone] ?? SKIN_TONES[0];
  const hair = HAIR_COLORS[config.hairColor] ?? HAIR_COLORS[0];
  const outfit = OUTFIT_COLORS[config.outfitColor] ?? OUTFIT_COLORS[0];

  return {
    S: skin,
    K: darken(skin, 0.15),
    O: '#0f0f1a',
    H: hair,
    C: outfit,
    D: darken(outfit, 0.15),
    L: lighten(outfit, 0.2),
    E: '#0f0f1a',
    W: '#ffffff',
    X: darken(outfit, 0.3),
    G: lighten(outfit, 0.3),
    B: darken(outfit, 0.25),
    P: darken(outfit, 0.3),
    R: darken(outfit, 0.4),
  };
}

/**
 * Resolve a color map for a fixed-color role (agent, not customizable).
 * Uses the role color as the outfit.
 */
export function resolveRoleColorMap(roleColor: string): Record<string, string> {
  const skin = '#fcd5b0';
  return {
    S: skin,
    K: darken(skin, 0.15),
    O: '#0f0f1a',
    H: '#4a3728',
    C: roleColor,
    D: darken(roleColor, 0.15),
    L: lighten(roleColor, 0.2),
    E: '#0f0f1a',
    W: '#ffffff',
    X: darken(roleColor, 0.3),
    G: lighten(roleColor, 0.3),
    B: darken(roleColor, 0.25),
    P: darken(roleColor, 0.3),
    R: darken(roleColor, 0.4),
  };
}

/**
 * Resolve environment colors from a named palette preset.
 * Returns the environment color map for tile/zone recoloring.
 */
export function resolveEnvironmentColorMap(presetName: string): PalettePreset['environment'] {
  const preset = PALETTE_PRESETS[presetName] ?? PALETTE_PRESETS.default;
  return { ...preset.environment };
}

/**
 * Resolve a themed color map by applying a preset's tint over an avatar config's colors.
 * If no preset is found or no avatarTint is defined, returns the standard map.
 */
export function resolveThemeColorMap(
  presetName: string,
  config: AvatarConfig,
): Record<string, string> {
  const preset = PALETTE_PRESETS[presetName];
  const base = resolveColorMap(config);

  if (!preset?.avatarTint) return base;

  const tintFactor = 0.15;
  const tintHex = preset.avatarTint;

  return {
    ...base,
    S: tint(base.S, tintHex, tintFactor * 0.5),
    K: tint(base.K, tintHex, tintFactor * 0.5),
    C: tint(base.C, tintHex, tintFactor),
    D: tint(base.D, tintHex, tintFactor),
    L: tint(base.L, tintHex, tintFactor),
    X: tint(base.X, tintHex, tintFactor),
    G: tint(base.G, tintHex, tintFactor),
    B: tint(base.B, tintHex, tintFactor),
    P: tint(base.P, tintHex, tintFactor),
    R: tint(base.R, tintHex, tintFactor),
  };
}
