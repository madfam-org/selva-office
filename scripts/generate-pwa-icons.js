/**
 * generate-pwa-icons.js
 *
 * Generates placeholder PWA icons (192x192 and 512x512) using @napi-rs/canvas.
 * These are simple branded squares with "S" — replace with real art later.
 *
 * Usage:
 *   node scripts/generate-pwa-icons.js
 */

const { createCanvas } = require('@napi-rs/canvas');
const fs = require('node:fs');
const path = require('node:path');

const ICONS_DIR = path.join(__dirname, '..', 'apps', 'office-ui', 'public', 'assets', 'icons');

const SIZES = [192, 512];

const BG_COLOR = '#1e1b4b'; // indigo-950 (theme_color)
const FG_COLOR = '#a5b4fc'; // indigo-300
const ACCENT_COLOR = '#6366f1'; // indigo-500

function generateIcon(size) {
  const canvas = createCanvas(size, size);
  const ctx = canvas.getContext('2d');

  // Background
  ctx.fillStyle = BG_COLOR;
  ctx.fillRect(0, 0, size, size);

  // Inner border / accent frame (2px at 192, 5px at 512)
  const borderWidth = Math.max(2, Math.round(size * 0.01));
  ctx.strokeStyle = ACCENT_COLOR;
  ctx.lineWidth = borderWidth;
  const inset = borderWidth * 3;
  ctx.strokeRect(inset, inset, size - inset * 2, size - inset * 2);

  // Pixel grid pattern in background (subtle)
  ctx.fillStyle = 'rgba(99, 102, 241, 0.08)'; // indigo-500 at 8%
  const gridSize = Math.round(size / 16);
  for (let y = 0; y < size; y += gridSize) {
    for (let x = 0; x < size; x += gridSize) {
      if ((x / gridSize + y / gridSize) % 2 === 0) {
        ctx.fillRect(x, y, gridSize, gridSize);
      }
    }
  }

  // Letter "S" centered
  const fontSize = Math.round(size * 0.5);
  ctx.fillStyle = FG_COLOR;
  ctx.font = `bold ${fontSize}px sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText('S', size / 2, size / 2 + Math.round(size * 0.02));

  return canvas.toBuffer('image/png');
}

// Ensure output directory exists
fs.mkdirSync(ICONS_DIR, { recursive: true });

for (const size of SIZES) {
  const buffer = generateIcon(size);
  const filePath = path.join(ICONS_DIR, `icon-${size}.png`);
  fs.writeFileSync(filePath, buffer);
  console.log(`Generated ${filePath} (${size}x${size})`);
}

console.log('PWA icons generated.');
