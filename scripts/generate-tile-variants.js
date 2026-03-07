#!/usr/bin/env node
/**
 * generate-tile-variants.js
 *
 * Applies palette presets to tile templates from tiles.json to produce
 * themed tileset PNGs. Each preset generates a drop-in replacement
 * for office-tileset.png.
 *
 * Usage:
 *   node scripts/generate-tile-variants.js [--presets all|name1,name2] [--output dir]
 */

const { createCanvas } = require('@napi-rs/canvas');
const fs = require('node:fs');
const path = require('node:path');
const { renderPixelData } = require('./sprite-data/renderer');
const tileTemplates = require('../packages/shared-types/src/sprite-data/tiles.json');
const palettePresets = require('../packages/shared-types/src/sprite-data/palette-presets.json');

const ALL_PRESETS = Object.keys(palettePresets.presets);

function parseArgs() {
  const args = process.argv.slice(2);
  let presets = ALL_PRESETS;
  let output = path.resolve(__dirname, '..', 'apps', 'office-ui', 'public', 'assets', 'tilesets', 'variants');

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--presets' && args[i + 1]) {
      const val = args[++i];
      presets = val === 'all' ? ALL_PRESETS : val.split(',');
    } else if (args[i] === '--output' && args[i + 1]) {
      output = path.resolve(args[++i]);
    }
  }
  return { presets, output };
}

/**
 * Tint a hex color used in the tile template toward the ambient tint.
 */
function tintColor(hex, tintHex, factor) {
  if (!tintHex || !hex || !hex.startsWith('#')) return hex;
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  const tr = parseInt(tintHex.slice(1, 3), 16);
  const tg = parseInt(tintHex.slice(3, 5), 16);
  const tb = parseInt(tintHex.slice(5, 7), 16);
  const clamp = (v) => Math.max(0, Math.min(255, Math.round(v)));
  return `#${clamp(r + (tr - r) * factor).toString(16).padStart(2, '0')}${clamp(g + (tg - g) * factor).toString(16).padStart(2, '0')}${clamp(b + (tb - b) * factor).toString(16).padStart(2, '0')}`;
}

/**
 * Create a tinted copy of a tile grid. Since tiles use direct hex colors,
 * we remap colors toward the preset's ambient tint.
 */
function tintGrid(grid, tintHex, factor) {
  if (!tintHex) return grid;
  return grid.map((row) =>
    row.map((cell) => {
      if (cell === null) return null;
      if (cell.startsWith('#')) return tintColor(cell, tintHex, factor);
      return cell;
    }),
  );
}

async function main() {
  const { presets, output } = parseArgs();

  fs.mkdirSync(output, { recursive: true });

  const tileOrder = [
    'floor', 'wall', 'desk',
    'dept_engineering', 'dept_sales', 'dept_support', 'dept_research',
    'review_station',
  ];

  let count = 0;

  for (const presetName of presets) {
    const preset = palettePresets.presets[presetName];
    if (!preset) {
      console.warn(`  warning: unknown preset "${presetName}", skipping`);
      continue;
    }

    const canvas = createCanvas(256, 32);
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, 256, 32);

    for (let i = 0; i < tileOrder.length; i++) {
      const tileGrid = tileTemplates[tileOrder[i]];
      if (!tileGrid) continue;

      const tintedGrid = tintGrid(tileGrid, preset.ambientTint, 0.2);
      renderPixelData(ctx, i * 32, 0, tintedGrid, {});
    }

    const filepath = path.join(output, `office-tileset-${presetName}.png`);
    fs.writeFileSync(filepath, canvas.toBuffer('image/png'));
    count++;
  }

  console.log(`Generated ${count} tileset variants in ${path.relative(process.cwd(), output)}`);
}

main().catch(console.error);
