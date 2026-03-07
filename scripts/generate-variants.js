#!/usr/bin/env node
/**
 * generate-variants.js
 *
 * Generates sprite variant PNGs by applying palette presets to
 * agent and tactician sprite templates.
 *
 * Usage:
 *   node scripts/generate-variants.js [--presets all|name1,name2] [--roles all|name1,name2] [--output dir]
 */

const { createCanvas } = require('@napi-rs/canvas');
const fs = require('node:fs');
const path = require('node:path');
const { buildVariantColorMap, composeAgentVariant, composeTacticianVariant } = require('./sprite-data/variation-combiner');

// ---------------------------------------------------------------------------
// Template data
// ---------------------------------------------------------------------------
const bodyTemplates = require('../packages/shared-types/src/sprite-data/body.json');
const hairTemplates = require('../packages/shared-types/src/sprite-data/hair.json');
const accessories = require('../packages/shared-types/src/sprite-data/accessories.json');
const palettePresets = require('../packages/shared-types/src/sprite-data/palette-presets.json');

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const BASE_COLORS = {
  tactician: '#6366f1',
  planner: '#8b5cf6',
  coder: '#06b6d4',
  reviewer: '#f59e0b',
  researcher: '#10b981',
  crm: '#f43f5e',
  support: '#0ea5e9',
};

const ROLE_ACCESSORY = {
  planner: 'clipboard',
  coder: 'laptop',
  reviewer: 'magnifier',
  researcher: 'book',
  crm: 'card',
  support: 'wrench',
};

const ALL_ROLES = Object.keys(ROLE_ACCESSORY);
const ALL_PRESETS = Object.keys(palettePresets.presets);

// ---------------------------------------------------------------------------
// CLI argument parsing
// ---------------------------------------------------------------------------
function parseArgs() {
  const args = process.argv.slice(2);
  let presets = ALL_PRESETS;
  let roles = [...ALL_ROLES, 'tactician'];
  let output = path.resolve(__dirname, '..', 'apps', 'office-ui', 'public', 'assets', 'sprites', 'variants');

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--presets' && args[i + 1]) {
      const val = args[++i];
      presets = val === 'all' ? ALL_PRESETS : val.split(',');
    } else if (args[i] === '--roles' && args[i + 1]) {
      const val = args[++i];
      roles = val === 'all' ? [...ALL_ROLES, 'tactician'] : val.split(',');
    } else if (args[i] === '--output' && args[i + 1]) {
      output = path.resolve(args[++i]);
    }
  }

  return { presets, roles, output };
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
async function main() {
  const { presets, roles, output } = parseArgs();

  fs.mkdirSync(output, { recursive: true });

  let count = 0;

  for (const presetName of presets) {
    const preset = palettePresets.presets[presetName];
    if (!preset) {
      console.warn(`  warning: unknown preset "${presetName}", skipping`);
      continue;
    }

    const presetDir = path.join(output, presetName);
    fs.mkdirSync(presetDir, { recursive: true });

    for (const role of roles) {
      const baseColor = BASE_COLORS[role] ?? BASE_COLORS.tactician;
      const colorMap = buildVariantColorMap(baseColor, {
        tintHex: preset.ambientTint,
        tintFactor: 0.15,
      });

      if (role === 'tactician') {
        // 384x32 (12 frames)
        const canvas = createCanvas(384, 32);
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, 384, 32);
        composeTacticianVariant(ctx, { bodyTemplates, hairTemplates, accessories, colorMap });
        const filepath = path.join(presetDir, 'tactician.png');
        fs.writeFileSync(filepath, canvas.toBuffer('image/png'));
        count++;
      } else {
        // 64x32 (2 frames)
        const canvas = createCanvas(64, 32);
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, 64, 32);
        composeAgentVariant(ctx, {
          bodyTemplates, hairTemplates, accessories,
          role, colorMap, roleAccessory: ROLE_ACCESSORY,
        });
        const filepath = path.join(presetDir, `agent-${role}.png`);
        fs.writeFileSync(filepath, canvas.toBuffer('image/png'));
        count++;
      }
    }
  }

  console.log(`Generated ${count} variant sprites across ${presets.length} presets in ${path.relative(process.cwd(), output)}`);
}

main().catch(console.error);
