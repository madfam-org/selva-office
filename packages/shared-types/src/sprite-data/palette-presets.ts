/**
 * Named palette presets that remap sprite tokens to themed color schemes.
 * Each preset maps the standard palette tokens (S, K, O, H, C, D, L, etc.)
 * to alternative colors, and provides environment colors for tiles/zones.
 */

export interface PalettePreset {
  /** Human-readable name */
  name: string;
  /** Optional tint applied to all avatar colors */
  avatarTint?: string;
  /** Environment overrides for tiles and department zones */
  environment: {
    floor: string;
    wall: string;
    deptEngineering: string;
    deptSales: string;
    deptSupport: string;
    deptResearch: string;
    reviewStation: string;
    ambientTint?: string;
    corridor?: string;
    lobby?: string;
    furnitureBase?: string;
    furnitureHighlight?: string;
    carpetEngineering?: string;
    carpetSales?: string;
    carpetSupport?: string;
    carpetResearch?: string;
    carpetBlueprint?: string;
  };
  /** Override outfit colors (index 0-3) for the preset */
  outfitOverrides?: string[];
}

export const PALETTE_PRESETS: Record<string, PalettePreset> = {
  default: {
    name: 'Default',
    environment: {
      floor: '#1e293b',
      wall: '#334155',
      deptEngineering: '#1e3a5f',
      deptSales: '#3b1e5f',
      deptSupport: '#1e5f3a',
      deptResearch: '#5f3a1e',
      reviewStation: '#fbbf24',
    },
  },
  cyberpunk: {
    name: 'Cyberpunk',
    avatarTint: '#ff00ff',
    environment: {
      floor: '#0a0a1a',
      wall: '#2a1a42',
      deptEngineering: '#0d1b3c',
      deptSales: '#2d0a3c',
      deptSupport: '#0d2b1c',
      deptResearch: '#3c1a0d',
      reviewStation: '#ff00ff',
      ambientTint: '#ff00ff',
    },
    outfitOverrides: ['#ff00ff', '#00ffff', '#ff3366', '#9933ff'],
  },
  forest: {
    name: 'Forest',
    avatarTint: '#2d5a1e',
    environment: {
      floor: '#1a2e1a',
      wall: '#2e3e2a',
      deptEngineering: '#1e3a2a',
      deptSales: '#2a3e1e',
      deptSupport: '#1e4a2e',
      deptResearch: '#3a2e1e',
      reviewStation: '#d4a017',
      ambientTint: '#4a7a3a',
    },
    outfitOverrides: ['#2d6a4f', '#40916c', '#74c69d', '#8b6914'],
  },
  desert: {
    name: 'Desert',
    avatarTint: '#c2956a',
    environment: {
      floor: '#3e2e1e',
      wall: '#5a4a3a',
      deptEngineering: '#4a3a2a',
      deptSales: '#5a4a2e',
      deptSupport: '#3a4a2e',
      deptResearch: '#6a4a2a',
      reviewStation: '#fbbf24',
      ambientTint: '#d4a574',
    },
    outfitOverrides: ['#c2956a', '#d4a574', '#a67c52', '#8b6914'],
  },
  arctic: {
    name: 'Arctic',
    avatarTint: '#a0c4e8',
    environment: {
      floor: '#1e2a3e',
      wall: '#2e3e5a',
      deptEngineering: '#1e3a5f',
      deptSales: '#2a3e6a',
      deptSupport: '#1e4a5a',
      deptResearch: '#3a4a5e',
      reviewStation: '#67e8f9',
      ambientTint: '#a0c4e8',
    },
    outfitOverrides: ['#60a5fa', '#38bdf8', '#a5b4fc', '#c7d2fe'],
  },
  ocean: {
    name: 'Ocean',
    avatarTint: '#0e7490',
    environment: {
      floor: '#0a1e2e',
      wall: '#1a2e3e',
      deptEngineering: '#0d2a4a',
      deptSales: '#1a3a5a',
      deptSupport: '#0d3a3e',
      deptResearch: '#1a2a5a',
      reviewStation: '#22d3ee',
      ambientTint: '#0e7490',
    },
    outfitOverrides: ['#0ea5e9', '#06b6d4', '#0891b2', '#0e7490'],
  },
  volcano: {
    name: 'Volcano',
    avatarTint: '#b91c1c',
    environment: {
      floor: '#1a0a0a',
      wall: '#3e2010',
      deptEngineering: '#3a1a0a',
      deptSales: '#4a1a0d',
      deptSupport: '#2a1a0a',
      deptResearch: '#4a2a0a',
      reviewStation: '#f59e0b',
      ambientTint: '#b91c1c',
    },
    outfitOverrides: ['#ef4444', '#f97316', '#fbbf24', '#dc2626'],
  },
  neon: {
    name: 'Neon',
    avatarTint: '#00ff88',
    environment: {
      floor: '#050510',
      wall: '#1e1e3a',
      deptEngineering: '#001a0a',
      deptSales: '#1a000a',
      deptSupport: '#000a1a',
      deptResearch: '#0a1a00',
      reviewStation: '#00ff88',
      ambientTint: '#00ff88',
    },
    outfitOverrides: ['#00ff88', '#ff0088', '#00ffff', '#ffff00'],
  },
  monochrome: {
    name: 'Monochrome',
    environment: {
      floor: '#1a1a1a',
      wall: '#333333',
      deptEngineering: '#2a2a2a',
      deptSales: '#303030',
      deptSupport: '#262626',
      deptResearch: '#343434',
      reviewStation: '#999999',
    },
    outfitOverrides: ['#666666', '#888888', '#aaaaaa', '#555555'],
  },
  pastel: {
    name: 'Pastel',
    avatarTint: '#f0e6ff',
    environment: {
      floor: '#2e2440',
      wall: '#4a4068',
      deptEngineering: '#2a3050',
      deptSales: '#3a2a50',
      deptSupport: '#2a4040',
      deptResearch: '#403030',
      reviewStation: '#fcd34d',
      ambientTint: '#e0d0f0',
    },
    outfitOverrides: ['#c4b5fd', '#a5b4fc', '#93c5fd', '#f9a8d4'],
  },
} as const;

export type PalettePresetName = keyof typeof PALETTE_PRESETS;
