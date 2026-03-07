/**
 * variation-combiner.js
 *
 * Combines body + hair + accessory layers with palette preset colors
 * to produce sprite variant sheets. Used by generate-variants.js.
 */

const { composeLayers } = require('./renderer');

/**
 * Build a color map for a given role color, with optional preset tint.
 */
function buildVariantColorMap(roleColor, opts = {}) {
  const { skinColor = '#fcd5b0', hairColor = '#4a3728', tintHex, tintFactor = 0.15 } = opts;

  function darken(hex, f) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `#${Math.max(0, Math.round(r * (1 - f))).toString(16).padStart(2, '0')}${Math.max(0, Math.round(g * (1 - f))).toString(16).padStart(2, '0')}${Math.max(0, Math.round(b * (1 - f))).toString(16).padStart(2, '0')}`;
  }

  function lighten(hex, f) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `#${Math.min(255, Math.round(r + (255 - r) * f)).toString(16).padStart(2, '0')}${Math.min(255, Math.round(g + (255 - g) * f)).toString(16).padStart(2, '0')}${Math.min(255, Math.round(b + (255 - b) * f)).toString(16).padStart(2, '0')}`;
  }

  function tint(hex, target, factor) {
    if (!target) return hex;
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    const tr = parseInt(target.slice(1, 3), 16);
    const tg = parseInt(target.slice(3, 5), 16);
    const tb = parseInt(target.slice(5, 7), 16);
    return `#${Math.round(r + (tr - r) * factor).toString(16).padStart(2, '0')}${Math.round(g + (tg - g) * factor).toString(16).padStart(2, '0')}${Math.round(b + (tb - b) * factor).toString(16).padStart(2, '0')}`;
  }

  const map = {
    S: skinColor,
    K: darken(skinColor, 0.15),
    O: '#0f0f1a',
    H: hairColor,
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

  if (tintHex) {
    for (const key of ['C', 'D', 'L', 'X', 'G', 'B', 'P', 'R']) {
      map[key] = tint(map[key], tintHex, tintFactor);
    }
    map.S = tint(map.S, tintHex, tintFactor * 0.5);
    map.K = tint(map.K, tintHex, tintFactor * 0.5);
  }

  return map;
}

/**
 * Generate a 2-frame agent variant sheet (idle + working) onto a canvas context.
 * @param {CanvasRenderingContext2D} ctx
 * @param {object} opts
 * @param {object} opts.bodyTemplates
 * @param {object} opts.hairTemplates
 * @param {object} opts.accessories
 * @param {string} opts.role
 * @param {Record<string, string>} opts.colorMap
 * @param {Record<string, string>} opts.roleAccessory - maps role to accessory key
 */
function composeAgentVariant(ctx, opts) {
  const { bodyTemplates, hairTemplates, accessories, role, colorMap, roleAccessory } = opts;

  // Frame 0: idle (front standing)
  const idleLayers = [bodyTemplates.front_stand];
  if (hairTemplates.short?.front) {
    idleLayers.push(hairTemplates.short.front);
  }
  composeLayers(ctx, 0, 0, idleLayers, colorMap);

  // Frame 1: working (right standing + role accessory)
  const workLayers = [bodyTemplates.right_stand];
  if (hairTemplates.short?.right) {
    workLayers.push(hairTemplates.short.right);
  }
  const accKey = roleAccessory[role];
  if (accKey && accessories.agent?.[accKey]) {
    workLayers.push(accessories.agent[accKey]);
  }
  composeLayers(ctx, 32, 0, workLayers, colorMap);
}

/**
 * Generate a 12-frame tactician variant sheet onto a canvas context.
 */
function composeTacticianVariant(ctx, opts) {
  const { bodyTemplates, hairTemplates, accessories, colorMap } = opts;
  const DIR_NAMES = ['front', 'left', 'back', 'right'];
  const WALK_NAMES = ['stand', 'walkL', 'walkR'];

  for (let dir = 0; dir < 4; dir++) {
    for (let walk = 0; walk < 3; walk++) {
      const frameIndex = dir * 3 + walk;
      const ox = frameIndex * 32;
      const dirName = DIR_NAMES[dir];
      const walkName = WALK_NAMES[walk];
      const bodyKey = `${dirName}_${walkName}`;
      const bodyGrid = bodyTemplates[bodyKey];
      const layers = [bodyGrid];

      if (hairTemplates.short?.[dirName]) {
        layers.push(hairTemplates.short[dirName]);
      }
      if (accessories.player?.crown) {
        layers.push(accessories.player.crown);
      }

      composeLayers(ctx, ox, 0, layers, colorMap);
    }
  }
}

module.exports = { buildVariantColorMap, composeAgentVariant, composeTacticianVariant };
