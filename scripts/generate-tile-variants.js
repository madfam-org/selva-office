#!/usr/bin/env node
/**
 * generate-tile-variants.js
 *
 * Applies palette presets to tile templates to produce themed tileset PNGs.
 * Each preset generates a drop-in replacement for office-tileset.png.
 *
 * New tiles use palette tokens (FL, WL, etc.) which are resolved to preset
 * environment colors. Original tiles use hex colors which are tinted.
 *
 * Usage:
 *   node scripts/generate-tile-variants.js [--presets all|name1,name2] [--output dir]
 */

const { createCanvas } = require('@napi-rs/canvas');
const fs = require('node:fs');
const path = require('node:path');
const { renderPixelData } = require('./sprite-data/renderer');
const { getAllTiles, buildEnvColorMap, TILE_ORDER, TILE_COLUMNS } = require('./sprite-data/tile-definitions');
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
 * Tint a hex color toward the ambient tint.
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
 * Resolve a tile grid's tokens to hex colors using the env color map,
 * then tint any remaining hex colors toward the ambient tint.
 */
function resolveAndTintGrid(grid, envColorMap, tintHex, tintFactor) {
  return grid.map((row) =>
    row.map((cell) => {
      if (cell === null) return null;
      // If it's a palette token, resolve it
      if (envColorMap[cell]) {
        const hex = envColorMap[cell];
        return tintHex ? tintColor(hex, tintHex, tintFactor * 0.5) : hex;
      }
      // If it's a hex color, tint it
      if (cell.startsWith('#')) {
        return tintHex ? tintColor(cell, tintHex, tintFactor) : cell;
      }
      return cell;
    }),
  );
}

async function main() {
  const { presets, output } = parseArgs();

  fs.mkdirSync(output, { recursive: true });

  const allTiles = getAllTiles();
  const cols = TILE_COLUMNS;
  const rows = Math.ceil(TILE_ORDER.length / cols);

  let count = 0;

  for (const presetName of presets) {
    const preset = palettePresets.presets[presetName];
    if (!preset) {
      console.warn(`  warning: unknown preset "${presetName}", skipping`);
      continue;
    }

    const canvas = createCanvas(cols * 32, rows * 32);
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, cols * 32, rows * 32);

    const envColorMap = buildEnvColorMap(preset);
    const tintHex = preset.ambientTint || null;

    for (let i = 0; i < TILE_ORDER.length; i++) {
      const name = TILE_ORDER[i];
      const tileGrid = allTiles[name];
      if (!tileGrid) continue;

      const resolvedGrid = resolveAndTintGrid(tileGrid, envColorMap, tintHex, 0.2);
      const col = i % cols;
      const row = Math.floor(i / cols);
      renderPixelData(ctx, col * 32, row * 32, resolvedGrid, {});
    }

    const filepath = path.join(output, `office-tileset-${presetName}.png`);
    fs.writeFileSync(filepath, canvas.toBuffer('image/png'));
    count++;
  }

  console.log(`Generated ${count} tileset variants in ${path.relative(process.cwd(), output)}`);
}

main().catch(console.error);
