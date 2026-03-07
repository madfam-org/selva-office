import Phaser from 'phaser';
import type { AvatarConfig } from '@autoswarm/shared-types';
import { SKIN_TONES, HAIR_COLORS, OUTFIT_COLORS } from '@autoswarm/shared-types';

/**
 * Generates a unique texture key for a given avatar configuration.
 * Uses a hash of the config values to enable caching.
 */
export function avatarTextureKey(config: AvatarConfig): string {
  return `avatar-${config.skinTone}-${config.hairStyle}-${config.hairColor}-${config.outfitColor}-${config.accessory}`;
}

/**
 * Composites avatar layers into a single 32x32 canvas texture.
 * Uses Phaser's createCanvas for runtime texture generation.
 *
 * The avatar is drawn pixel-by-pixel matching the style from generate-assets.js:
 * - Head (8x8) with skin tone
 * - Eyes
 * - Hair overlay based on style
 * - Body (8x12) with outfit color
 * - Legs
 * - Accessory overlay
 */
export function compositeAvatar(scene: Phaser.Scene, config: AvatarConfig): string {
  const key = avatarTextureKey(config);

  // Return cached if already exists
  if (scene.textures.exists(key)) {
    return key;
  }

  const canvas = scene.textures.createCanvas(key, 32, 32);
  if (!canvas) return 'tactician'; // fallback

  const ctx = canvas.getContext();
  ctx.clearRect(0, 0, 32, 32);

  const skinColor = SKIN_TONES[config.skinTone] ?? SKIN_TONES[0];
  const outfitColor = OUTFIT_COLORS[config.outfitColor] ?? OUTFIT_COLORS[0];
  const hairColor = HAIR_COLORS[config.hairColor] ?? HAIR_COLORS[0];

  const cx = 12; // character center-x (8px wide head starts here)
  const cy = 4;  // top of head

  // Head (8x8)
  ctx.fillStyle = skinColor;
  ctx.fillRect(cx, cy, 8, 8);
  drawOutline(ctx, cx, cy, 8, 8);

  // Eyes
  ctx.fillStyle = '#0f0f1a';
  ctx.fillRect(cx + 2, cy + 3, 2, 2);
  ctx.fillRect(cx + 5, cy + 3, 2, 2);

  // Hair (if not bald)
  if (config.hairStyle >= 0) {
    ctx.fillStyle = hairColor;
    switch (config.hairStyle) {
      case 0: // Short
        ctx.fillRect(cx, cy, 8, 3);
        break;
      case 1: // Long
        ctx.fillRect(cx - 1, cy, 10, 4);
        ctx.fillRect(cx - 1, cy + 4, 2, 6);
        ctx.fillRect(cx + 7, cy + 4, 2, 6);
        break;
      case 2: // Spiky
        ctx.fillRect(cx, cy - 2, 8, 2);
        ctx.fillRect(cx + 1, cy - 3, 2, 1);
        ctx.fillRect(cx + 4, cy - 4, 2, 2);
        ctx.fillRect(cx + 6, cy - 3, 2, 1);
        break;
      case 3: // Curly
        ctx.fillRect(cx - 1, cy - 1, 10, 4);
        ctx.fillRect(cx - 1, cy + 3, 2, 2);
        ctx.fillRect(cx + 7, cy + 3, 2, 2);
        break;
    }
  }

  // Body (8x12)
  ctx.fillStyle = darken(outfitColor, 0.15);
  ctx.fillRect(cx, cy + 8, 8, 12);
  drawOutline(ctx, cx, cy + 8, 8, 12);

  // Outfit accent (upper body)
  ctx.fillStyle = outfitColor;
  ctx.fillRect(cx + 1, cy + 9, 6, 5);

  // Legs (2x 4x4)
  const legY = cy + 20;
  ctx.fillStyle = darken(outfitColor, 0.3);
  ctx.fillRect(cx, legY, 4, 4);
  drawOutline(ctx, cx, legY, 4, 4);
  ctx.fillRect(cx + 4, legY, 4, 4);
  drawOutline(ctx, cx + 4, legY, 4, 4);

  // Accessories
  if (config.accessory >= 0) {
    switch (config.accessory) {
      case 0: // Glasses
        ctx.strokeStyle = '#374151';
        ctx.lineWidth = 1;
        ctx.strokeRect(cx + 1, cy + 2, 3, 3);
        ctx.strokeRect(cx + 5, cy + 2, 3, 3);
        ctx.beginPath();
        ctx.moveTo(cx + 4, cy + 3);
        ctx.lineTo(cx + 5, cy + 3);
        ctx.stroke();
        break;
      case 1: // Crown
        ctx.fillStyle = '#fbbf24';
        ctx.fillRect(cx + 1, cy - 3, 6, 2);
        ctx.fillRect(cx + 1, cy - 4, 2, 1);
        ctx.fillRect(cx + 3, cy - 5, 2, 2);
        ctx.fillRect(cx + 5, cy - 4, 2, 1);
        ctx.fillStyle = '#ef4444';
        ctx.fillRect(cx + 3, cy - 4, 2, 1);
        break;
      case 2: // Headphones
        ctx.strokeStyle = '#374151';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(cx + 4, cy, 5, Math.PI, 0);
        ctx.stroke();
        ctx.fillStyle = '#374151';
        ctx.fillRect(cx - 1, cy - 1, 3, 4);
        ctx.fillRect(cx + 6, cy - 1, 3, 4);
        break;
      case 3: // Hat
        ctx.fillStyle = '#4a5568';
        ctx.fillRect(cx - 2, cy - 2, 12, 3);
        ctx.fillRect(cx, cy - 5, 8, 4);
        break;
    }
  }

  canvas.refresh();
  return key;
}

function drawOutline(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number): void {
  ctx.strokeStyle = '#0f0f1a';
  ctx.lineWidth = 1;
  ctx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);
}

function darken(hex: string, factor: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgb(${Math.round(r * (1 - factor))},${Math.round(g * (1 - factor))},${Math.round(b * (1 - factor))})`;
}
