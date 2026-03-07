import { describe, it, expect } from 'vitest';
import {
  PALETTE_PRESETS,
  saturate,
  hueShift,
  tint,
  darken,
  lighten,
  resolveEnvironmentColorMap,
  resolveThemeColorMap,
  resolveColorMap,
} from '../sprite-data';
import type { AvatarConfig } from '../avatar';

const HEX_RE = /^#[0-9a-f]{6}$/;

const DEFAULT_CONFIG: AvatarConfig = {
  skinTone: 0,
  hairStyle: 0,
  hairColor: 0,
  outfitColor: 0,
  accessory: -1,
};

describe('saturate', () => {
  it('returns valid hex for factor > 1', () => {
    expect(saturate('#6366f1', 1.5)).toMatch(HEX_RE);
  });

  it('returns valid hex for factor < 1', () => {
    expect(saturate('#6366f1', 0.5)).toMatch(HEX_RE);
  });

  it('returns grayscale for factor 0', () => {
    const result = saturate('#ff0000', 0);
    expect(result).toMatch(HEX_RE);
    // Pure red desaturated should be equal R=G=B
    const r = parseInt(result.slice(1, 3), 16);
    const g = parseInt(result.slice(3, 5), 16);
    const b = parseInt(result.slice(5, 7), 16);
    expect(r).toBe(g);
    expect(g).toBe(b);
  });
});

describe('hueShift', () => {
  it('returns valid hex', () => {
    expect(hueShift('#ff0000', 120)).toMatch(HEX_RE);
  });

  it('360 degree shift returns roughly same color', () => {
    const original = '#6366f1';
    const shifted = hueShift(original, 360);
    // Should be very close to original (allow rounding)
    const [or, og, ob] = [
      parseInt(original.slice(1, 3), 16),
      parseInt(original.slice(3, 5), 16),
      parseInt(original.slice(5, 7), 16),
    ];
    const [sr, sg, sb] = [
      parseInt(shifted.slice(1, 3), 16),
      parseInt(shifted.slice(3, 5), 16),
      parseInt(shifted.slice(5, 7), 16),
    ];
    expect(Math.abs(or - sr)).toBeLessThanOrEqual(1);
    expect(Math.abs(og - sg)).toBeLessThanOrEqual(1);
    expect(Math.abs(ob - sb)).toBeLessThanOrEqual(1);
  });

  it('handles negative degrees', () => {
    expect(hueShift('#ff0000', -120)).toMatch(HEX_RE);
  });
});

describe('tint', () => {
  it('returns valid hex', () => {
    expect(tint('#ffffff', '#ff0000', 0.5)).toMatch(HEX_RE);
  });

  it('factor 0 returns original color', () => {
    expect(tint('#abcdef', '#000000', 0)).toBe('#abcdef');
  });

  it('factor 1 returns tint color', () => {
    expect(tint('#000000', '#ff8040', 1)).toBe('#ff8040');
  });
});

describe('darken and lighten (refactored)', () => {
  it('darken factor 0 returns same color', () => {
    expect(darken('#ffffff', 0)).toBe('#ffffff');
  });

  it('darken factor 1 returns black', () => {
    expect(darken('#ffffff', 1)).toBe('#000000');
  });

  it('lighten factor 0 returns same color', () => {
    expect(lighten('#808080', 0)).toBe('#808080');
  });

  it('lighten factor 1 returns white', () => {
    expect(lighten('#000000', 1)).toBe('#ffffff');
  });
});

describe('PALETTE_PRESETS', () => {
  it('has at least 10 presets', () => {
    expect(Object.keys(PALETTE_PRESETS).length).toBeGreaterThanOrEqual(10);
  });

  it('each preset has a name and environment colors', () => {
    for (const [key, preset] of Object.entries(PALETTE_PRESETS)) {
      expect(preset.name).toBeTruthy();
      expect(preset.environment.floor).toMatch(HEX_RE);
      expect(preset.environment.wall).toMatch(HEX_RE);
      expect(preset.environment.deptEngineering).toMatch(HEX_RE);
      expect(preset.environment.deptSales).toMatch(HEX_RE);
      expect(preset.environment.deptSupport).toMatch(HEX_RE);
      expect(preset.environment.deptResearch).toMatch(HEX_RE);
      expect(preset.environment.reviewStation).toMatch(HEX_RE);

      if (preset.environment.ambientTint) {
        expect(preset.environment.ambientTint).toMatch(HEX_RE);
      }
    }
  });

  it('includes the default preset', () => {
    expect(PALETTE_PRESETS.default).toBeDefined();
  });

  it('outfit overrides (if defined) are valid hex arrays', () => {
    for (const preset of Object.values(PALETTE_PRESETS)) {
      if (preset.outfitOverrides) {
        expect(preset.outfitOverrides.length).toBeGreaterThanOrEqual(1);
        for (const color of preset.outfitOverrides) {
          expect(color).toMatch(HEX_RE);
        }
      }
    }
  });
});

describe('resolveEnvironmentColorMap', () => {
  it('returns default environment for unknown preset', () => {
    const env = resolveEnvironmentColorMap('nonexistent');
    expect(env.floor).toBe(PALETTE_PRESETS.default.environment.floor);
  });

  it('returns cyberpunk environment for "cyberpunk"', () => {
    const env = resolveEnvironmentColorMap('cyberpunk');
    expect(env.floor).toBe('#0a0a1a');
    expect(env.reviewStation).toBe('#ff00ff');
  });
});

describe('resolveThemeColorMap', () => {
  it('returns standard map for default preset', () => {
    const themed = resolveThemeColorMap('default', DEFAULT_CONFIG);
    const standard = resolveColorMap(DEFAULT_CONFIG);
    expect(themed.S).toBe(standard.S);
    expect(themed.C).toBe(standard.C);
  });

  it('applies tint for presets with avatarTint', () => {
    const standard = resolveColorMap(DEFAULT_CONFIG);
    const themed = resolveThemeColorMap('cyberpunk', DEFAULT_CONFIG);
    // Outfit should be shifted from the tint
    expect(themed.C).not.toBe(standard.C);
    expect(themed.C).toMatch(HEX_RE);
  });

  it('preserves eye and outline colors', () => {
    const themed = resolveThemeColorMap('neon', DEFAULT_CONFIG);
    expect(themed.O).toBe('#0f0f1a');
    expect(themed.E).toBe('#0f0f1a');
    expect(themed.W).toBe('#ffffff');
  });
});

describe('minimum contrast ratios', () => {
  function relativeLuminance(hex: string): number {
    const [r, g, b] = [
      parseInt(hex.slice(1, 3), 16) / 255,
      parseInt(hex.slice(3, 5), 16) / 255,
      parseInt(hex.slice(5, 7), 16) / 255,
    ].map((c) => (c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)));
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  }

  function contrastRatio(hex1: string, hex2: string): number {
    const l1 = relativeLuminance(hex1);
    const l2 = relativeLuminance(hex2);
    const lighter = Math.max(l1, l2);
    const darker = Math.min(l1, l2);
    return (lighter + 0.05) / (darker + 0.05);
  }

  it('review station has at least 3:1 contrast against floor in all presets', () => {
    for (const [name, preset] of Object.entries(PALETTE_PRESETS)) {
      const ratio = contrastRatio(preset.environment.reviewStation, preset.environment.floor);
      expect(ratio).toBeGreaterThanOrEqual(3);
    }
  });

  it('wall has at least 1.2:1 contrast against floor in all presets', () => {
    for (const [name, preset] of Object.entries(PALETTE_PRESETS)) {
      const ratio = contrastRatio(preset.environment.wall, preset.environment.floor);
      expect(ratio).toBeGreaterThanOrEqual(1.2);
    }
  });
});
