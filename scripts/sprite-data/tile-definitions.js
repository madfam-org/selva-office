/**
 * tile-definitions.js
 *
 * Programmatically generates all 79 tile grids (32x32) for the office tileset.
 * Solarpunk aesthetic inspired by Final Fantasy Pixel Remaster: warm wood,
 * bamboo, living greenery, botanical departments, soft golden light.
 *
 * Original 8 tiles are now generated here (overriding tiles.json) to use
 * palette tokens (FL, WL, WH, etc.) for full theme-ability via palette presets.
 *
 * Tile index layout: 16 columns x 5 rows = 512x160 PNG
 */

const tileTemplates = require('../../packages/shared-types/src/sprite-data/tiles.json');

// ---------------------------------------------------------------------------
// Drawing primitives
// ---------------------------------------------------------------------------

/** Create a 32x32 grid filled with a value */
function grid(v = null) {
  return Array.from({ length: 32 }, () => Array(32).fill(v));
}

/** Fill a rectangle */
function fill(g, x, y, w, h, v) {
  for (let r = y; r < y + h && r < 32; r++) {
    for (let c = x; c < x + w && c < 32; c++) {
      if (r >= 0 && c >= 0) g[r][c] = v;
    }
  }
}

/** Horizontal line */
function hline(g, x, y, len, v) {
  for (let c = x; c < x + len && c < 32; c++) {
    if (y >= 0 && y < 32 && c >= 0) g[y][c] = v;
  }
}

/** Vertical line */
function vline(g, x, y, len, v) {
  for (let r = y; r < y + len && r < 32; r++) {
    if (r >= 0 && x >= 0 && x < 32) g[r][x] = v;
  }
}

/** Single pixel */
function px(g, x, y, v) {
  if (y >= 0 && y < 32 && x >= 0 && x < 32) g[y][x] = v;
}

/** Rectangle border (outline only) */
function rect(g, x, y, w, h, v) {
  hline(g, x, y, w, v);
  hline(g, x, y + h - 1, w, v);
  vline(g, x, y, h, v);
  vline(g, x + w - 1, y, h, v);
}

/** Filled circle (approximate at pixel scale) */
function circle(g, cx, cy, r, v) {
  for (let y = -r; y <= r; y++) {
    for (let x = -r; x <= r; x++) {
      if (x * x + y * y <= r * r) {
        px(g, cx + x, cy + y, v);
      }
    }
  }
}

/** Checkerboard pattern */
function checker(g, x, y, w, h, v1, v2, size) {
  for (let r = y; r < y + h && r < 32; r++) {
    for (let c = x; c < x + w && c < 32; c++) {
      if (r >= 0 && c >= 0) {
        const cx = Math.floor((c - x) / size);
        const cy = Math.floor((r - y) / size);
        g[r][c] = (cx + cy) % 2 === 0 ? v1 : v2;
      }
    }
  }
}

/** Stripe pattern (horizontal lines every N rows) */
function hstripes(g, x, y, w, h, base, stripe, every) {
  fill(g, x, y, w, h, base);
  for (let r = y; r < y + h && r < 32; r++) {
    if ((r - y) % every === 0) hline(g, x, r, w, stripe);
  }
}

/** Grid pattern */
function gridPattern(g, x, y, w, h, base, line, every) {
  fill(g, x, y, w, h, base);
  for (let r = y; r < y + h && r < 32; r++) {
    if ((r - y) % every === 0) hline(g, x, r, w, line);
  }
  for (let c = x; c < x + w && c < 32; c++) {
    if ((c - x) % every === 0) vline(g, c, y, h, line);
  }
}

/** Diamond pattern */
function diamonds(g, x, y, w, h, base, accent, size) {
  fill(g, x, y, w, h, base);
  for (let r = y; r < y + h && r < 32; r++) {
    for (let c = x; c < x + w && c < 32; c++) {
      const lr = (r - y) % size;
      const lc = (c - x) % size;
      const half = Math.floor(size / 2);
      if (Math.abs(lr - half) + Math.abs(lc - half) === half) {
        if (r >= 0 && c >= 0) g[r][c] = accent;
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Solarpunk color constants (used alongside palette tokens for fixed accents)
// ---------------------------------------------------------------------------
const SOLAR_GOLD = '#f6d55c';     // solar panel / sunlight accent
const MOSS_LIGHT = '#68b684';     // light moss green
const MOSS_MID = '#4a9e6e';       // mid moss (same as AC default)
const MOSS_DARK = '#2d6a4a';      // dark moss
const SKY_BLUE = '#87ceeb';       // daylight sky
const VINE_GREEN = '#3aad62';     // climbing vine
const LEAF_BRIGHT = '#5de88a';    // sun-dappled leaf
const STONE_WARM = '#9a8a6a';     // warm sandstone
const STONE_LIGHT = '#b8a888';    // light stone
const CYAN_GLOW = '#67e8f9';      // monitor / tech glow
const TERRACOTTA = '#b87a4a';     // pot / warm clay
const SOIL_DARK = '#3d2b1f';      // potting soil
const BARK_MID = '#6b4226';       // tree bark

// ---------------------------------------------------------------------------
// Original 8 tiles (indices 0-7) — solarpunk versions using palette tokens
// ---------------------------------------------------------------------------

/** Floor (index 0): Wood plank pattern with grain lines */
function floorBase() {
  const g = grid('FL');
  // Alternating plank bands (4px wide) with FD shadow between planks
  for (let r = 0; r < 32; r++) {
    const band = Math.floor(r / 4);
    if (r % 4 === 0) {
      // Plank seam
      hline(g, 0, r, 32, 'FD');
    } else if (r % 4 === 2) {
      // Grain highlight line — offset per plank for variety
      const offset = (band * 7) % 5;
      for (let c = offset; c < 32; c += 8) {
        hline(g, c, r, 3, 'FH');
      }
    }
  }
  // Occasional wood knots
  px(g, 7, 5, 'FS');
  px(g, 8, 5, 'FD');
  px(g, 22, 17, 'FS');
  px(g, 23, 17, 'FD');
  px(g, 14, 27, 'FS');
  return g;
}

/** Wall (index 1): Bamboo panel with moss strip at bottom */
function wallBase() {
  const g = grid('WL');
  // Vertical bamboo stalks (4px apart, 2px wide)
  for (let c = 2; c < 32; c += 4) {
    vline(g, c, 0, 30, 'WD');       // stalk shadow
    vline(g, c + 1, 0, 30, 'WL');   // stalk body
    vline(g, c - 1, 0, 30, 'WH');   // stalk highlight (left edge)
    // Bamboo node rings every 8 rows
    for (let r = 3; r < 30; r += 8) {
      px(g, c - 1, r, 'WD');
      px(g, c, r, 'WD');
      px(g, c + 1, r, 'WD');
    }
  }
  // 2px living moss strip at bottom
  hline(g, 0, 30, 32, 'AC');
  hline(g, 0, 31, 32, MOSS_DARK);
  // Tiny bright moss highlights
  px(g, 5, 30, MOSS_LIGHT);
  px(g, 14, 30, MOSS_LIGHT);
  px(g, 23, 30, MOSS_LIGHT);
  px(g, 28, 31, VINE_GREEN);
  return g;
}

/** Desk (index 2): Organic wood desk with rounded corners and tiny plant */
function deskBase() {
  const g = grid('FL');
  // Desk surface (rounded corners via missing corner pixels)
  fill(g, 5, 7, 22, 14, 'FN');
  // Rounded corners (cut 2px diagonals)
  px(g, 5, 7, 'FL'); px(g, 6, 7, 'FL');
  px(g, 26, 7, 'FL'); px(g, 25, 7, 'FL');  // top-left shifted: 5+22-1=26
  px(g, 5, 20, 'FL'); px(g, 6, 20, 'FL');
  px(g, 26, 20, 'FL'); px(g, 25, 20, 'FL');
  // Wood grain (horizontal)
  for (let r = 9; r < 19; r += 2) {
    hline(g, 7, r, 18, 'FH');
  }
  // Highlight top edge
  hline(g, 7, 8, 18, 'FH');
  // Shadow bottom-right
  hline(g, 7, 19, 18, 'FS');
  vline(g, 26, 8, 12, 'FS');
  // Legs (warm wood)
  fill(g, 7, 21, 3, 4, 'FS');
  fill(g, 22, 21, 3, 4, 'FS');
  // Tiny potted plant in top-right corner
  px(g, 23, 9, TERRACOTTA);
  px(g, 24, 9, TERRACOTTA);
  px(g, 23, 8, 'AC');
  px(g, 24, 8, MOSS_LIGHT);
  px(g, 23, 7, VINE_GREEN);
  return g;
}

/** Dept Engineering (index 3): Tech greenhouse floor */
function deptEngineering() {
  const g = grid('CE');
  // Inset wood plank pattern (every 6 rows)
  for (let r = 2; r < 30; r += 6) {
    hline(g, 4, r, 24, 'FL');
    hline(g, 4, r + 1, 24, 'FD');
  }
  // Moss patch clusters (organic, scattered)
  px(g, 6, 8, 'AC'); px(g, 7, 8, 'AC'); px(g, 7, 9, MOSS_LIGHT);
  px(g, 20, 14, 'AC'); px(g, 21, 14, MOSS_LIGHT); px(g, 20, 15, 'AC');
  px(g, 12, 22, 'AC'); px(g, 13, 22, 'AC'); px(g, 13, 23, MOSS_LIGHT);
  px(g, 26, 6, MOSS_LIGHT); px(g, 27, 7, 'AC');
  // Solar gold accent dots (sunlight through greenhouse roof)
  px(g, 10, 5, SOLAR_GOLD);
  px(g, 22, 11, SOLAR_GOLD);
  px(g, 15, 19, SOLAR_GOLD);
  px(g, 28, 25, SOLAR_GOLD);
  px(g, 5, 27, SOLAR_GOLD);
  // Subtle circuit-trace pattern (tech element)
  hline(g, 2, 16, 6, 'FD');
  vline(g, 8, 16, 4, 'FD');
  hline(g, 24, 20, 6, 'FD');
  return g;
}

/** Dept Sales (index 4): Market garden floor */
function deptSales() {
  const g = grid('CS');
  // Warm wood insets (parquet pattern)
  for (let r = 0; r < 32; r += 8) {
    for (let c = 0; c < 32; c += 8) {
      fill(g, c + 2, r + 2, 4, 4, 'FL');
      fill(g, c + 3, r + 3, 2, 2, 'FD');
    }
  }
  // Herb-green border accents
  hline(g, 0, 0, 32, 'AC');
  hline(g, 0, 31, 32, 'AC');
  vline(g, 0, 0, 32, 'AC');
  vline(g, 31, 0, 32, 'AC');
  // Inner green dotted border
  for (let c = 2; c < 30; c += 3) {
    px(g, c, 2, MOSS_LIGHT);
    px(g, c, 29, MOSS_LIGHT);
  }
  // Golden decorative pixel pattern (market stall flourish)
  px(g, 8, 8, SOLAR_GOLD); px(g, 24, 8, SOLAR_GOLD);
  px(g, 8, 24, SOLAR_GOLD); px(g, 24, 24, SOLAR_GOLD);
  px(g, 16, 16, SOLAR_GOLD);
  return g;
}

/** Dept Support (index 5): Zen garden floor */
function deptSupport() {
  const g = grid('CU');
  // Alternating gravel texture (checkerboard of CU and lighter variant)
  for (let r = 0; r < 32; r++) {
    for (let c = 0; c < 32; c++) {
      if ((r + c) % 3 === 0) g[r][c] = '#4a6a4a'; // slightly lighter CU
    }
  }
  // Stepping stones (warm grey rounded rectangles)
  fill(g, 6, 6, 6, 6, '#8a8a7a');
  px(g, 6, 6, 'CU'); px(g, 11, 6, 'CU'); px(g, 6, 11, 'CU'); px(g, 11, 11, 'CU');
  fill(g, 20, 14, 6, 6, '#8a8a7a');
  px(g, 20, 14, 'CU'); px(g, 25, 14, 'CU'); px(g, 20, 19, 'CU'); px(g, 25, 19, 'CU');
  fill(g, 10, 22, 6, 6, '#8a8a7a');
  px(g, 10, 22, 'CU'); px(g, 15, 22, 'CU'); px(g, 10, 27, 'CU'); px(g, 15, 27, 'CU');
  // Stone highlights
  px(g, 8, 8, '#9a9a8a'); px(g, 22, 16, '#9a9a8a'); px(g, 12, 24, '#9a9a8a');
  // Green accent border
  hline(g, 0, 0, 32, 'AC'); hline(g, 0, 31, 32, 'AC');
  vline(g, 0, 0, 32, 'AC'); vline(g, 31, 0, 32, 'AC');
  return g;
}

/** Dept Research (index 6): Library garden floor */
function deptResearch() {
  const g = grid('CR');
  // Dark wood bookshelf-adjacent areas along edges
  fill(g, 0, 0, 4, 32, 'FS');
  fill(g, 28, 0, 4, 32, 'FS');
  // Teal carpet pattern (herringbone)
  for (let r = 2; r < 30; r += 4) {
    for (let c = 6; c < 26; c += 4) {
      // Diagonal pair
      px(g, c, r, '#3a5a6a');
      px(g, c + 1, r + 1, '#3a5a6a');
      px(g, c + 2, r, '#3a5a6a');
      px(g, c + 1, r + 2, 'CR');
    }
  }
  // Vine accents along bookshelf edges
  px(g, 4, 5, 'AC'); px(g, 4, 12, VINE_GREEN); px(g, 4, 20, 'AC'); px(g, 4, 28, VINE_GREEN);
  px(g, 27, 3, VINE_GREEN); px(g, 27, 10, 'AC'); px(g, 27, 18, VINE_GREEN); px(g, 27, 26, 'AC');
  // Small leaf sprites climbing up
  px(g, 3, 4, MOSS_LIGHT); px(g, 28, 9, LEAF_BRIGHT);
  return g;
}

/** Review Station (index 7): Glass-roofed gazebo floor */
function reviewStation() {
  const g = grid(STONE_WARM);
  // Golden accent border (2px)
  rect(g, 0, 0, 32, 32, SOLAR_GOLD);
  rect(g, 1, 1, 30, 30, SOLAR_GOLD);
  // Inner stone
  fill(g, 2, 2, 28, 28, STONE_WARM);
  // Circular oak medallion in center
  circle(g, 16, 16, 8, 'FN');
  circle(g, 16, 16, 6, 'FH');
  circle(g, 16, 16, 4, 'FN');
  circle(g, 16, 16, 2, SOLAR_GOLD);
  // Stone texture dots
  px(g, 5, 5, STONE_LIGHT); px(g, 26, 5, STONE_LIGHT);
  px(g, 5, 26, STONE_LIGHT); px(g, 26, 26, STONE_LIGHT);
  px(g, 10, 3, '#847a5a'); px(g, 22, 28, '#847a5a');
  // Approval icon (check mark) in gold center
  px(g, 14, 16, '#ffffff'); px(g, 15, 17, '#ffffff');
  px(g, 16, 16, '#ffffff'); px(g, 17, 15, '#ffffff');
  px(g, 18, 14, '#ffffff');
  return g;
}

// ---------------------------------------------------------------------------
// Wall tiles (12) — indices 8-19: Bamboo/sandstone solarpunk walls
// ---------------------------------------------------------------------------

/** Wall at top of room — bamboo panel with moss accent at bottom face */
function wallTop() {
  const g = grid('WL');
  // Top shadow edge
  fill(g, 0, 0, 32, 3, 'WD');
  // Vertical bamboo stalks
  for (let c = 3; c < 32; c += 4) {
    vline(g, c, 3, 23, 'WD');
    if (c + 1 < 32) vline(g, c - 1, 3, 23, 'WH');
  }
  // Bamboo node rings
  for (let c = 3; c < 32; c += 4) {
    px(g, c, 10, 'WD'); px(g, c, 18, 'WD');
  }
  // Bottom face (highlight, facing room below) with moss strip
  fill(g, 0, 26, 32, 3, 'WH');
  // Baseboard
  fill(g, 0, 29, 32, 3, 'WD');
  // Living moss accent on baseboard
  hline(g, 0, 29, 32, 'AC');
  px(g, 4, 29, MOSS_LIGHT); px(g, 12, 29, MOSS_LIGHT);
  px(g, 20, 29, MOSS_LIGHT); px(g, 28, 29, MOSS_LIGHT);
  return g;
}

/** Wall at bottom of room — face/highlight on top edge */
function wallBottom() {
  const g = grid('WL');
  // Top face (highlight, facing room above)
  fill(g, 0, 0, 32, 3, 'WH');
  // Moss accent on top face
  hline(g, 0, 2, 32, 'AC');
  px(g, 6, 2, MOSS_LIGHT); px(g, 18, 2, MOSS_LIGHT);
  // Vertical bamboo stalks
  for (let c = 3; c < 32; c += 4) {
    vline(g, c, 3, 24, 'WD');
    if (c + 1 < 32) vline(g, c - 1, 3, 24, 'WH');
  }
  // Horizontal detail
  hline(g, 0, 18, 32, 'WD');
  hline(g, 0, 19, 32, 'WD');
  // Bottom shadow
  fill(g, 0, 29, 32, 3, 'WD');
  return g;
}

/** Wall at left of room — face/highlight on right edge */
function wallLeft() {
  const g = grid('WL');
  // Left shadow
  fill(g, 0, 0, 3, 32, 'WD');
  // Horizontal bamboo detail
  for (let r = 3; r < 32; r += 4) {
    hline(g, 3, r, 23, 'WD');
    if (r - 1 >= 0) hline(g, 3, r - 1, 23, 'WH');
  }
  // Right face (highlight, facing room)
  fill(g, 26, 0, 3, 32, 'WH');
  // Moss accent on right face
  vline(g, 26, 0, 32, 'AC');
  px(g, 26, 8, MOSS_LIGHT); px(g, 26, 20, MOSS_LIGHT);
  // Baseboard right
  fill(g, 29, 0, 3, 32, 'WD');
  return g;
}

/** Wall at right of room — face/highlight on left edge */
function wallRight() {
  const g = grid('WL');
  // Right shadow
  fill(g, 29, 0, 3, 32, 'WD');
  // Horizontal bamboo detail
  for (let r = 3; r < 32; r += 4) {
    hline(g, 6, r, 23, 'WD');
    if (r - 1 >= 0) hline(g, 6, r - 1, 23, 'WH');
  }
  // Left face (highlight)
  fill(g, 3, 0, 3, 32, 'WH');
  // Moss accent on left face
  vline(g, 5, 0, 32, 'AC');
  px(g, 5, 6, MOSS_LIGHT); px(g, 5, 16, MOSS_LIGHT); px(g, 5, 26, MOSS_LIGHT);
  // Baseboard left
  fill(g, 0, 0, 3, 32, 'WD');
  return g;
}

/** Outer corner: top-left (room is to bottom-right) */
function wallCornerTL() {
  const g = grid('WL');
  fill(g, 0, 0, 3, 32, 'WD');   // left shadow
  fill(g, 0, 0, 32, 3, 'WD');   // top shadow
  fill(g, 26, 0, 3, 32, 'WH');  // right face
  fill(g, 0, 26, 32, 3, 'WH');  // bottom face
  fill(g, 29, 0, 3, 32, 'WD');  // right baseboard
  fill(g, 0, 29, 32, 3, 'WD');  // bottom baseboard
  // Corner detail — bamboo weave
  fill(g, 26, 26, 6, 6, 'WH');
  // Moss on inner corner
  px(g, 26, 29, 'AC'); px(g, 29, 26, 'AC');
  return g;
}

/** Outer corner: top-right (room is to bottom-left) */
function wallCornerTR() {
  const g = grid('WL');
  fill(g, 29, 0, 3, 32, 'WD');  // right shadow
  fill(g, 0, 0, 32, 3, 'WD');   // top shadow
  fill(g, 3, 0, 3, 32, 'WH');   // left face
  fill(g, 0, 26, 32, 3, 'WH');  // bottom face
  fill(g, 0, 0, 3, 32, 'WD');   // left baseboard
  fill(g, 0, 29, 32, 3, 'WD');  // bottom baseboard
  fill(g, 0, 26, 6, 6, 'WH');
  px(g, 2, 29, 'AC'); px(g, 5, 26, 'AC');
  return g;
}

/** Outer corner: bottom-left (room is to top-right) */
function wallCornerBL() {
  const g = grid('WL');
  fill(g, 0, 0, 3, 32, 'WD');   // left shadow
  fill(g, 0, 29, 32, 3, 'WD');  // bottom shadow
  fill(g, 26, 0, 3, 32, 'WH');  // right face
  fill(g, 0, 0, 32, 3, 'WH');   // top face
  fill(g, 29, 0, 3, 32, 'WD');  // right baseboard
  fill(g, 26, 0, 6, 3, 'WH');
  px(g, 26, 2, 'AC'); px(g, 29, 2, 'AC');
  return g;
}

/** Outer corner: bottom-right (room is to top-left) */
function wallCornerBR() {
  const g = grid('WL');
  fill(g, 29, 0, 3, 32, 'WD');  // right shadow
  fill(g, 0, 29, 32, 3, 'WD');  // bottom shadow
  fill(g, 3, 0, 3, 32, 'WH');   // left face
  fill(g, 0, 0, 32, 3, 'WH');   // top face
  fill(g, 0, 0, 3, 32, 'WD');   // left baseboard
  fill(g, 0, 0, 6, 3, 'WH');
  px(g, 2, 2, 'AC'); px(g, 5, 2, 'AC');
  return g;
}

/** Inner corner: top-left (concave, wall fills TL quadrant) */
function wallInnerTL() {
  const g = grid('FL');
  fill(g, 0, 0, 16, 16, 'WL');
  fill(g, 0, 0, 16, 2, 'WD');
  fill(g, 0, 0, 2, 16, 'WD');
  hline(g, 0, 15, 16, 'WH');
  vline(g, 15, 0, 16, 'WH');
  // Moss on inner edges
  hline(g, 4, 15, 8, 'AC');
  vline(g, 15, 4, 8, 'AC');
  fill(g, 16, 0, 16, 3, 'WL');
  fill(g, 16, 0, 16, 1, 'WD');
  hline(g, 16, 2, 16, 'WH');
  fill(g, 0, 16, 3, 16, 'WL');
  vline(g, 0, 16, 16, 'WD');
  vline(g, 2, 16, 16, 'WH');
  return g;
}

/** Inner corner: top-right */
function wallInnerTR() {
  const g = grid('FL');
  fill(g, 16, 0, 16, 16, 'WL');
  fill(g, 16, 0, 16, 2, 'WD');
  fill(g, 30, 0, 2, 16, 'WD');
  hline(g, 16, 15, 16, 'WH');
  vline(g, 16, 0, 16, 'WH');
  hline(g, 20, 15, 8, 'AC');
  vline(g, 16, 4, 8, 'AC');
  fill(g, 0, 0, 16, 3, 'WL');
  fill(g, 0, 0, 16, 1, 'WD');
  hline(g, 0, 2, 16, 'WH');
  fill(g, 29, 16, 3, 16, 'WL');
  vline(g, 31, 16, 16, 'WD');
  vline(g, 29, 16, 16, 'WH');
  return g;
}

/** Inner corner: bottom-left */
function wallInnerBL() {
  const g = grid('FL');
  fill(g, 0, 16, 16, 16, 'WL');
  fill(g, 0, 30, 16, 2, 'WD');
  fill(g, 0, 16, 2, 16, 'WD');
  hline(g, 0, 16, 16, 'WH');
  vline(g, 15, 16, 16, 'WH');
  hline(g, 4, 16, 8, 'AC');
  vline(g, 15, 20, 8, 'AC');
  fill(g, 0, 29, 16, 3, 'WL');
  hline(g, 0, 29, 16, 'WH');
  fill(g, 0, 0, 3, 16, 'WL');
  vline(g, 0, 0, 16, 'WD');
  vline(g, 2, 0, 16, 'WH');
  fill(g, 16, 29, 16, 3, 'WL');
  hline(g, 16, 29, 16, 'WH');
  fill(g, 16, 31, 16, 1, 'WD');
  return g;
}

/** Inner corner: bottom-right */
function wallInnerBR() {
  const g = grid('FL');
  fill(g, 16, 16, 16, 16, 'WL');
  fill(g, 16, 30, 16, 2, 'WD');
  fill(g, 30, 16, 2, 16, 'WD');
  hline(g, 16, 16, 16, 'WH');
  vline(g, 16, 16, 16, 'WH');
  hline(g, 20, 16, 8, 'AC');
  vline(g, 16, 20, 8, 'AC');
  fill(g, 29, 0, 3, 16, 'WL');
  vline(g, 31, 0, 16, 'WD');
  vline(g, 29, 0, 16, 'WH');
  fill(g, 0, 29, 16, 3, 'WL');
  hline(g, 0, 29, 16, 'WH');
  fill(g, 0, 31, 16, 1, 'WD');
  return g;
}

// ---------------------------------------------------------------------------
// Floor tiles (8) — indices 20-27: Solarpunk sandstone and botanical carpets
// ---------------------------------------------------------------------------

/** Corridor floor — sandstone cobble path (index 20) */
function floorCorridor() {
  const g = grid('FL');
  // Cobble pattern: alternating shade blocks every 8px
  for (let r = 0; r < 32; r += 8) {
    for (let c = 0; c < 32; c += 8) {
      const shade = ((r / 8 + c / 8) % 2 === 0) ? 'FD' : 'FL';
      fill(g, c, r, 8, 8, shade);
    }
  }
  // Cobble mortar lines
  for (let r = 0; r < 32; r += 8) {
    hline(g, 0, r, 32, STONE_WARM);
  }
  for (let c = 0; c < 32; c += 8) {
    vline(g, c, 0, 32, STONE_WARM);
  }
  // Occasional moss in mortar
  px(g, 0, 8, 'AC'); px(g, 16, 0, MOSS_LIGHT); px(g, 8, 24, 'AC');
  return g;
}

/** Lobby floor — bright sandstone with decorative border (index 21) */
function floorLobby() {
  const g = grid('FL');
  // Lighter sandstone fill
  fill(g, 0, 0, 32, 32, STONE_LIGHT);
  // Decorative border (2px)
  rect(g, 0, 0, 32, 32, 'FN');
  rect(g, 1, 1, 30, 30, 'FH');
  // Welcome mat feel: warm inner area
  fill(g, 4, 4, 24, 24, 'FL');
  // Diamond accent in center
  px(g, 16, 14, SOLAR_GOLD); px(g, 15, 15, SOLAR_GOLD); px(g, 17, 15, SOLAR_GOLD);
  px(g, 14, 16, SOLAR_GOLD); px(g, 18, 16, SOLAR_GOLD);
  px(g, 15, 17, SOLAR_GOLD); px(g, 17, 17, SOLAR_GOLD); px(g, 16, 18, SOLAR_GOLD);
  return g;
}

/** Department carpet with botanical border trim */
function floorCarpet(token) {
  const g = grid(token);
  // Border trim (vine-like)
  rect(g, 0, 0, 32, 32, 'AC');
  rect(g, 1, 1, 30, 30, 'FD');
  // Corner leaf accents
  px(g, 2, 2, MOSS_LIGHT); px(g, 29, 2, MOSS_LIGHT);
  px(g, 2, 29, MOSS_LIGHT); px(g, 29, 29, MOSS_LIGHT);
  // Subtle inner pattern with organic spacing
  for (let r = 5; r < 27; r += 5) {
    for (let c = 5; c < 27; c += 5) {
      px(g, c, r, 'FD');
    }
  }
  return g;
}

/** Grid floor — warm wood parquet grid */
function floorGrid() {
  const g = grid('FL');
  gridPattern(g, 0, 0, 32, 32, 'FL', 'FD', 4);
  // Parquet detail: alternating grain direction in each cell
  for (let r = 0; r < 32; r += 4) {
    for (let c = 0; c < 32; c += 4) {
      if ((r / 4 + c / 4) % 2 === 0) {
        // Horizontal grain
        hline(g, c + 1, r + 2, 2, 'FH');
      } else {
        // Vertical grain
        vline(g, c + 2, r + 1, 2, 'FH');
      }
    }
  }
  return g;
}

// ---------------------------------------------------------------------------
// Furniture tiles (15) — indices 28-42: Warm wood with green accents
// ---------------------------------------------------------------------------

/** Desk viewed from front (top-down, facing south) */
function deskFront() {
  const g = grid('FL');
  // Desk surface (warm wood)
  fill(g, 4, 6, 24, 16, 'FN');
  // Wood grain
  for (let r = 8; r < 20; r += 3) {
    hline(g, 6, r, 20, 'FH');
  }
  // Highlight top edge
  hline(g, 4, 6, 24, 'FH');
  // Shadow bottom
  hline(g, 4, 21, 24, 'FS');
  // Legs
  fill(g, 5, 22, 3, 4, 'FS');
  fill(g, 24, 22, 3, 4, 'FS');
  // Drawer handle (golden)
  fill(g, 14, 18, 4, 1, SOLAR_GOLD);
  // Small plant on desk
  px(g, 24, 8, TERRACOTTA);
  px(g, 24, 7, 'AC');
  px(g, 25, 7, MOSS_LIGHT);
  return g;
}

/** Desk viewed from side */
function deskSide() {
  const g = grid('FL');
  fill(g, 8, 6, 16, 14, 'FN');
  // Wood grain
  for (let r = 8; r < 18; r += 3) {
    hline(g, 10, r, 12, 'FH');
  }
  hline(g, 8, 6, 16, 'FH');
  vline(g, 8, 6, 14, 'FH');
  hline(g, 8, 19, 16, 'FS');
  vline(g, 23, 6, 14, 'FS');
  // Legs (warm tapered)
  fill(g, 9, 20, 2, 6, 'FS');
  fill(g, 21, 20, 2, 6, 'FS');
  return g;
}

/** Chair from above */
function chair() {
  const g = grid('FL');
  // Seat (warm wood + fabric)
  fill(g, 10, 12, 12, 12, 'FN');
  fill(g, 10, 12, 12, 2, 'FH');
  fill(g, 10, 22, 12, 2, 'FS');
  // Back rest
  fill(g, 10, 6, 12, 6, 'FS');
  fill(g, 10, 6, 12, 1, 'FN');
  // Cushion with green fabric accent
  fill(g, 12, 14, 8, 6, 'AC');
  fill(g, 13, 15, 6, 4, MOSS_LIGHT);
  // Wheels
  px(g, 9, 25, 'FS');
  px(g, 22, 25, 'FS');
  px(g, 9, 11, 'FS');
  px(g, 22, 11, 'FS');
  return g;
}

/** Monitor (off) */
function monitor() {
  const g = grid('FL');
  // Screen (dark)
  fill(g, 6, 4, 20, 14, '#1a1a2e');
  rect(g, 5, 3, 22, 16, 'FS');
  // Bezel highlight (warm wood frame)
  hline(g, 6, 3, 20, 'FH');
  vline(g, 5, 4, 14, 'FH');
  // Stand (warm wood)
  fill(g, 13, 19, 6, 3, 'FN');
  fill(g, 10, 22, 12, 2, 'FN');
  hline(g, 10, 22, 12, 'FH');
  return g;
}

/** Monitor (on — cyan glow) */
function monitorOn() {
  const g = grid('FL');
  // Screen (lit with soft cyan)
  fill(g, 6, 4, 20, 14, '#0a3a4a');
  fill(g, 8, 6, 16, 10, CYAN_GLOW);
  // Text lines on screen
  for (let r = 7; r < 15; r += 2) {
    hline(g, 9, r, 8 + (r % 4), '#0a3a4a');
  }
  rect(g, 5, 3, 22, 16, 'FS');
  hline(g, 6, 3, 20, 'FH');
  // Stand (warm wood)
  fill(g, 13, 19, 6, 3, 'FN');
  fill(g, 10, 22, 12, 2, 'FN');
  hline(g, 10, 22, 12, 'FH');
  return g;
}

/** Bookshelf (tall, warm wood with colored books) */
function bookshelf() {
  const g = grid('FL');
  // Shelf frame (warm wood)
  fill(g, 4, 2, 24, 28, 'FN');
  rect(g, 3, 1, 26, 30, 'FS');
  hline(g, 4, 1, 24, 'FH');
  // Shelves
  for (let r = 8; r < 28; r += 7) {
    hline(g, 4, r, 24, 'FH');
    hline(g, 4, r + 1, 24, 'FS');
  }
  // Books (botanical/earthy tones)
  const bookColors = [MOSS_DARK, '#8b5e3c', 'AC', SOLAR_GOLD, '#7a4a3a', TERRACOTTA];
  for (let shelf = 0; shelf < 3; shelf++) {
    const shelfY = 3 + shelf * 7;
    for (let b = 0; b < 6; b++) {
      const bx = 6 + b * 3;
      fill(g, bx, shelfY, 2, 5, bookColors[(shelf * 6 + b) % bookColors.length]);
    }
  }
  // Small trailing vine on top shelf
  px(g, 5, 3, 'AC'); px(g, 6, 4, VINE_GREEN);
  return g;
}

/** Small potted plant (fern with terracotta pot) */
function plantSmall() {
  const g = grid('FL');
  // Terracotta pot
  fill(g, 12, 22, 8, 6, TERRACOTTA);
  fill(g, 13, 21, 6, 1, STONE_WARM);
  hline(g, 12, 27, 8, BARK_MID);
  // Soil
  fill(g, 13, 22, 6, 2, SOIL_DARK);
  // Fern fronds (multiple shades radiating outward)
  fill(g, 13, 14, 6, 8, 'AC');
  fill(g, 11, 16, 2, 4, 'AC');
  fill(g, 19, 16, 2, 4, 'AC');
  fill(g, 14, 12, 4, 2, VINE_GREEN);
  px(g, 15, 11, VINE_GREEN);
  px(g, 16, 11, VINE_GREEN);
  // Highlights (sunlit tips)
  px(g, 14, 15, LEAF_BRIGHT);
  px(g, 17, 17, LEAF_BRIGHT);
  px(g, 11, 17, MOSS_LIGHT);
  px(g, 20, 17, MOSS_LIGHT);
  // Dark stems
  vline(g, 15, 14, 4, MOSS_DARK);
  vline(g, 16, 14, 4, MOSS_DARK);
  return g;
}

/** Large plant / small tree (warm pot, lush canopy) */
function plantLarge() {
  const g = grid('FL');
  // Large terracotta pot
  fill(g, 10, 24, 12, 6, TERRACOTTA);
  fill(g, 11, 23, 10, 1, STONE_WARM);
  hline(g, 10, 29, 12, BARK_MID);
  fill(g, 11, 24, 10, 2, SOIL_DARK);
  // Trunk (warm bark)
  fill(g, 14, 18, 4, 6, BARK_MID);
  fill(g, 15, 18, 2, 6, '#5c3a1e');
  // Lush canopy (multiple green layers)
  circle(g, 16, 12, 8, MOSS_DARK);
  circle(g, 13, 10, 5, 'AC');
  circle(g, 19, 10, 5, 'AC');
  circle(g, 16, 8, 5, VINE_GREEN);
  circle(g, 14, 6, 3, LEAF_BRIGHT);
  circle(g, 18, 7, 2, LEAF_BRIGHT);
  // Golden light highlights
  px(g, 12, 7, SOLAR_GOLD);
  px(g, 20, 6, SOLAR_GOLD);
  return g;
}

/** Whiteboard (warm wood frame) */
function whiteboard() {
  const g = grid('FL');
  // Board frame (warm wood)
  fill(g, 3, 3, 26, 20, 'FN');
  // White surface
  fill(g, 4, 4, 24, 18, '#f0ebe0');
  // Marker scribbles (botanical color scheme)
  hline(g, 6, 7, 12, 'AC');
  hline(g, 6, 9, 16, 'AC');
  hline(g, 6, 12, 10, TERRACOTTA);
  hline(g, 6, 14, 14, TERRACOTTA);
  hline(g, 6, 17, 8, SOLAR_GOLD);
  // Marker tray
  fill(g, 6, 23, 20, 2, 'FS');
  fill(g, 8, 23, 3, 1, 'AC');
  fill(g, 12, 23, 3, 1, TERRACOTTA);
  fill(g, 16, 23, 3, 1, SOLAR_GOLD);
  return g;
}

/** Water cooler (warm wood body, blue water) */
function waterCooler() {
  const g = grid('FL');
  // Water jug (top)
  fill(g, 12, 2, 8, 10, '#bfdbfe');
  fill(g, 13, 1, 6, 1, '#93c5fd');
  fill(g, 14, 0, 4, 1, '#60a5fa');
  // Water level
  fill(g, 12, 6, 8, 6, '#3b82f6');
  // Body (warm wood instead of cold metal)
  fill(g, 10, 12, 12, 14, 'FN');
  fill(g, 10, 12, 12, 1, 'FH');
  vline(g, 10, 12, 14, 'FH');
  vline(g, 21, 12, 14, 'FS');
  hline(g, 10, 25, 12, 'FS');
  // Tap
  fill(g, 18, 16, 3, 2, 'FH');
  px(g, 20, 18, '#3b82f6');
  // Legs
  fill(g, 11, 26, 2, 4, 'FS');
  fill(g, 19, 26, 2, 4, 'FS');
  return g;
}

/** Coffee machine (warm wood body) */
function coffeeMachine() {
  const g = grid('FL');
  // Body (warm wood)
  fill(g, 8, 6, 16, 20, 'FN');
  fill(g, 8, 6, 16, 1, 'FH');
  vline(g, 8, 6, 20, 'FH');
  vline(g, 23, 6, 20, 'FS');
  hline(g, 8, 25, 16, 'FS');
  // Display (green LED)
  fill(g, 11, 8, 10, 4, '#1a2e1a');
  fill(g, 12, 9, 8, 2, 'AC');
  // Brew area
  fill(g, 11, 14, 10, 6, SOIL_DARK);
  // Cup (ceramic)
  fill(g, 13, 17, 6, 3, '#f0ebe0');
  fill(g, 12, 17, 1, 3, STONE_WARM);
  // Steam
  px(g, 15, 14, STONE_LIGHT);
  px(g, 16, 13, STONE_LIGHT);
  px(g, 17, 14, STONE_LIGHT);
  // Base
  fill(g, 10, 26, 12, 2, 'FS');
  return g;
}

/** Filing cabinet (warm wood) */
function filingCabinet() {
  const g = grid('FL');
  // Cabinet body
  fill(g, 6, 4, 20, 24, 'FN');
  rect(g, 5, 3, 22, 26, 'FS');
  hline(g, 6, 3, 20, 'FH');
  vline(g, 5, 3, 26, 'FH');
  // Drawers (3)
  for (let i = 0; i < 3; i++) {
    const dy = 5 + i * 7;
    hline(g, 7, dy, 18, 'FS');
    hline(g, 7, dy + 6, 18, 'FS');
    // Handle (golden)
    fill(g, 14, dy + 2, 4, 2, SOLAR_GOLD);
  }
  // Tiny vine accent on top
  px(g, 24, 4, 'AC');
  px(g, 25, 3, VINE_GREEN);
  return g;
}

/** Server rack (warm wood frame housing tech) */
function serverRack() {
  const g = grid('FL');
  // Rack body (dark with warm wood frame)
  fill(g, 4, 2, 24, 28, '#2d2d2e');
  rect(g, 3, 1, 26, 30, 'FN');
  hline(g, 4, 1, 24, 'FH');
  // Server units
  for (let i = 0; i < 5; i++) {
    const sy = 3 + i * 5;
    fill(g, 6, sy, 20, 4, '#374141');
    hline(g, 6, sy, 20, '#4b5553');
    // Vent holes
    for (let c = 8; c < 20; c += 3) {
      px(g, c, sy + 2, '#1f2927');
    }
    // LED indicators (green = healthy, gold = active)
    px(g, 22, sy + 1, 'AC');
    px(g, 24, sy + 1, SOLAR_GOLD);
  }
  return g;
}

/** Printer (warm wood accents) */
function printer() {
  const g = grid('FL');
  // Body (warm wood)
  fill(g, 6, 10, 20, 14, 'FN');
  fill(g, 6, 10, 20, 1, 'FH');
  vline(g, 6, 10, 14, 'FH');
  vline(g, 25, 10, 14, 'FS');
  hline(g, 6, 23, 20, 'FS');
  // Paper tray top
  fill(g, 8, 6, 16, 4, 'FN');
  fill(g, 9, 6, 14, 2, '#f0ebe0');
  // Output tray
  fill(g, 10, 24, 12, 3, 'FN');
  fill(g, 11, 24, 10, 2, '#f0ebe0');
  // Display
  fill(g, 9, 13, 6, 3, '#1a2e1a');
  fill(g, 10, 14, 4, 1, 'AC');
  // Buttons
  px(g, 18, 14, CYAN_GLOW);
  px(g, 20, 14, TERRACOTTA);
  return g;
}

/** Couch (green fabric with wood frame) */
function couch() {
  const g = grid('FL');
  // Backrest (dark wood)
  fill(g, 4, 4, 24, 8, 'FS');
  hline(g, 4, 4, 24, 'FN');
  fill(g, 4, 4, 24, 2, 'FN');
  // Seat cushions (green fabric)
  fill(g, 4, 12, 24, 12, 'AC');
  // Cushion divider
  vline(g, 16, 12, 12, MOSS_DARK);
  // Cushion highlights
  hline(g, 5, 13, 10, MOSS_LIGHT);
  hline(g, 17, 13, 10, MOSS_LIGHT);
  // Armrests (warm wood)
  fill(g, 2, 6, 2, 18, 'FN');
  fill(g, 28, 6, 2, 18, 'FN');
  // Shadow
  hline(g, 4, 23, 24, MOSS_DARK);
  fill(g, 2, 24, 2, 4, 'FS');
  fill(g, 28, 24, 2, 4, 'FS');
  return g;
}

// ---------------------------------------------------------------------------
// Station tiles (3) — indices 43-45: Solarpunk gazebo / botanical stations
// ---------------------------------------------------------------------------

/** Review station v2 — solar-powered approval pedestal */
function reviewStationV2() {
  const g = grid('FL');
  // Pedestal base (warm stone)
  circle(g, 16, 22, 8, 'FS');
  circle(g, 16, 22, 6, 'FN');
  circle(g, 16, 22, 4, 'FH');
  // Column (warm wood)
  fill(g, 14, 12, 4, 10, 'FN');
  vline(g, 14, 12, 10, 'FH');
  vline(g, 17, 12, 10, 'FS');
  // Solar golden display (approval glow)
  fill(g, 8, 4, 16, 8, SOLAR_GOLD);
  fill(g, 10, 5, 12, 6, '#fde68a');
  fill(g, 11, 6, 10, 4, '#fffbe6');
  // Approval check icon
  px(g, 14, 7, 'AC');
  px(g, 15, 8, 'AC');
  px(g, 16, 7, 'AC');
  px(g, 17, 6, 'AC');
  // Solar gold glow particles
  px(g, 9, 3, SOLAR_GOLD);
  px(g, 22, 3, SOLAR_GOLD);
  px(g, 7, 6, '#fde68a');
  px(g, 24, 6, '#fde68a');
  // Tiny vine on pedestal
  px(g, 18, 18, 'AC'); px(g, 19, 19, VINE_GREEN);
  return g;
}

/** Dispatch terminal — bamboo-framed terminal with cyan screen */
function dispatchTerminal() {
  const g = grid('FL');
  // Terminal body (dark with bamboo frame)
  fill(g, 8, 8, 16, 18, '#2d2d2e');
  rect(g, 7, 7, 18, 20, 'FN');
  hline(g, 8, 7, 16, 'FH');
  // Screen
  fill(g, 10, 9, 12, 8, '#0a3a4a');
  fill(g, 11, 10, 10, 6, CYAN_GLOW);
  // Scan line
  hline(g, 11, 12, 10, '#0a3a4a');
  // "> _" prompt
  px(g, 12, 13, '#0a3a4a');
  px(g, 14, 13, '#0a3a4a');
  // Keyboard (warm tones)
  fill(g, 9, 19, 14, 3, 'FN');
  for (let c = 10; c < 22; c += 2) {
    px(g, c, 20, 'FH');
  }
  // Accent stripe (green)
  hline(g, 8, 23, 16, 'AC');
  // Base (warm wood)
  fill(g, 10, 26, 12, 2, 'FN');
  hline(g, 10, 26, 12, 'FH');
  return g;
}

/** Blueprint table — warm wood drafting table with botanical sketch */
function blueprintTable() {
  const g = grid('FL');
  // Table surface (warm wood)
  fill(g, 3, 6, 26, 20, 'FN');
  rect(g, 2, 5, 28, 22, 'FS');
  hline(g, 3, 5, 26, 'FH');
  // Blueprint paper (warm-tinted instead of cold blue)
  fill(g, 5, 8, 22, 16, '#2a4a3a');
  gridPattern(g, 5, 8, 22, 16, '#2a4a3a', '#3a5a4a', 4);
  // Drawing on blueprint (botanical/architecture lines)
  hline(g, 8, 12, 10, CYAN_GLOW);
  vline(g, 18, 12, 8, CYAN_GLOW);
  hline(g, 12, 20, 6, CYAN_GLOW);
  vline(g, 8, 12, 4, CYAN_GLOW);
  // Pencil
  fill(g, 22, 10, 1, 6, SOLAR_GOLD);
  px(g, 22, 16, '#374151');
  // Ruler (warm wood)
  fill(g, 6, 22, 16, 1, 'FH');
  // Legs
  fill(g, 4, 26, 2, 4, 'FS');
  fill(g, 26, 26, 2, 4, 'FS');
  return g;
}

// ---------------------------------------------------------------------------
// Decoration tiles (8) — indices 46-53: Solarpunk botanical decor
// ---------------------------------------------------------------------------

/** Round rug (green/gold botanical pattern) */
function rugRound() {
  const g = grid('FL');
  circle(g, 16, 16, 12, 'AC');
  circle(g, 16, 16, 10, MOSS_DARK);
  circle(g, 16, 16, 8, 'AC');
  // Pattern dots (golden)
  for (let a = 0; a < 8; a++) {
    const angle = (a / 8) * Math.PI * 2;
    const rx = Math.round(16 + Math.cos(angle) * 6);
    const ry = Math.round(16 + Math.sin(angle) * 6);
    px(g, rx, ry, SOLAR_GOLD);
  }
  return g;
}

/** Poster A — botanical illustration */
function posterA() {
  const g = grid('FL');
  // Frame (warm wood)
  fill(g, 6, 2, 20, 26, 'FN');
  fill(g, 7, 3, 18, 24, '#f0ebe0');
  // Botanical shapes (leaf patterns)
  fill(g, 9, 5, 8, 8, 'AC');
  fill(g, 13, 9, 8, 8, MOSS_DARK);
  fill(g, 11, 14, 8, 8, VINE_GREEN);
  // Overlaps
  fill(g, 13, 9, 4, 4, MOSS_LIGHT);
  fill(g, 13, 14, 6, 3, LEAF_BRIGHT);
  // Golden specimen label
  hline(g, 10, 24, 12, SOLAR_GOLD);
  return g;
}

/** Poster B — growth chart with botanical theme */
function posterB() {
  const g = grid('FL');
  // Frame (warm wood)
  fill(g, 6, 2, 20, 26, 'FN');
  fill(g, 7, 3, 18, 24, '#f0ebe0');
  // Bar chart (green/gold tones)
  fill(g, 10, 20, 3, 5, 'AC');
  fill(g, 14, 16, 3, 9, MOSS_DARK);
  fill(g, 18, 12, 3, 13, SOLAR_GOLD);
  // Title lines
  hline(g, 9, 5, 14, 'FS');
  hline(g, 9, 7, 10, STONE_WARM);
  return g;
}

/** Clock (warm wood frame) */
function clock() {
  const g = grid('FL');
  // Clock face (warm wood rim)
  circle(g, 16, 14, 8, 'FN');
  circle(g, 16, 14, 7, '#f0ebe0');
  circle(g, 16, 14, 6, '#f8f4ea');
  // Hour markers
  px(g, 16, 8, 'FS');
  px(g, 22, 14, 'FS');
  px(g, 16, 20, 'FS');
  px(g, 10, 14, 'FS');
  // Hands
  vline(g, 16, 10, 4, 'FS');
  hline(g, 16, 14, 4, TERRACOTTA);
  // Center dot (golden)
  px(g, 16, 14, SOLAR_GOLD);
  return g;
}

/** Ceiling light (warm golden glow) */
function ceilingLight() {
  const g = grid('FL');
  // Warm golden glow fixture
  circle(g, 16, 16, 6, SOLAR_GOLD);
  circle(g, 16, 16, 4, '#fde68a');
  circle(g, 16, 16, 2, '#fffbe6');
  // Warm glow halo on floor
  for (let y = 6; y <= 26; y++) {
    for (let x = 6; x <= 26; x++) {
      const dx = x - 16;
      const dy = y - 16;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist >= 6 && dist <= 10 && g[y][x] === 'FL') {
        g[y][x] = 'FH'; // warm glow ring on floor
      }
    }
  }
  return g;
}

/** Horizontal door (opening in a horizontal wall, warm wood frame) */
function doorH() {
  const g = grid('WL');
  // Door opening in center
  fill(g, 8, 0, 16, 32, 'FL');
  // Door frame (warm wood)
  vline(g, 7, 0, 32, 'FN');
  vline(g, 24, 0, 32, 'FN');
  vline(g, 6, 0, 32, 'FS');
  vline(g, 25, 0, 32, 'FS');
  // Threshold (golden accent)
  fill(g, 8, 14, 16, 4, 'FH');
  hline(g, 8, 14, 16, SOLAR_GOLD);
  hline(g, 8, 17, 16, SOLAR_GOLD);
  return g;
}

/** Vertical door (opening in a vertical wall, warm wood frame) */
function doorV() {
  const g = grid('WL');
  // Door opening in center
  fill(g, 0, 8, 32, 16, 'FL');
  // Door frame (warm wood)
  hline(g, 0, 7, 32, 'FN');
  hline(g, 0, 24, 32, 'FN');
  hline(g, 0, 6, 32, 'FS');
  hline(g, 0, 25, 32, 'FS');
  // Threshold (golden accent)
  fill(g, 14, 8, 4, 16, 'FH');
  vline(g, 14, 8, 16, SOLAR_GOLD);
  vline(g, 17, 8, 16, SOLAR_GOLD);
  return g;
}

/** Welcome mat (natural woven with green trim) */
function welcomeMat() {
  const g = grid('FL');
  // Mat body (woven natural fiber)
  fill(g, 4, 10, 24, 12, 'FN');
  fill(g, 5, 11, 22, 10, 'FH');
  // Woven texture
  for (let r = 11; r < 21; r += 2) {
    for (let c = 5; c < 27; c += 2) {
      px(g, c, r, 'FN');
    }
  }
  // Green border decoration
  rect(g, 6, 12, 20, 8, 'AC');
  // "HI" text (warm gold)
  vline(g, 10, 13, 5, SOLAR_GOLD);
  vline(g, 13, 13, 5, SOLAR_GOLD);
  hline(g, 10, 15, 4, SOLAR_GOLD);
  vline(g, 17, 13, 5, SOLAR_GOLD);
  hline(g, 16, 13, 3, SOLAR_GOLD);
  hline(g, 16, 17, 3, SOLAR_GOLD);
  return g;
}

// ---------------------------------------------------------------------------
// FFVI-quality tiles (25) — indices 54-78: Solarpunk enriched
// ---------------------------------------------------------------------------

/** Desk with horizontal wood grain (rich solarpunk wood) */
function deskWood() {
  const g = grid('FL');
  // Desk surface with wood grain
  fill(g, 4, 6, 24, 16, 'FN');
  // Wood grain: alternating horizontal lines
  for (let r = 7; r < 21; r++) {
    if (r % 3 === 0) hline(g, 5, r, 22, 'FH');
    else if (r % 3 === 1) hline(g, 5, r, 22, 'FN');
    else hline(g, 5, r, 22, 'FS');
  }
  // Highlight top edge
  hline(g, 4, 6, 24, 'FH');
  // Shadow bottom
  hline(g, 4, 21, 24, 'FS');
  // Legs
  fill(g, 5, 22, 3, 4, 'FS');
  fill(g, 24, 22, 3, 4, 'FS');
  // Knot details
  px(g, 14, 12, 'FS');
  px(g, 15, 12, 'FS');
  px(g, 22, 16, 'FS');
  // Golden drawer handle
  fill(g, 14, 18, 4, 1, SOLAR_GOLD);
  return g;
}

/** Desk with coffee mug and steam wisps */
function deskWithCoffee() {
  const g = grid('FL');
  // Desk surface
  fill(g, 4, 6, 24, 16, 'FN');
  hline(g, 4, 6, 24, 'FH');
  hline(g, 4, 21, 24, 'FS');
  fill(g, 5, 22, 3, 4, 'FS');
  fill(g, 24, 22, 3, 4, 'FS');
  // Coffee mug (ceramic/terracotta)
  circle(g, 22, 13, 3, TERRACOTTA);
  circle(g, 22, 13, 2, '#5c3a1e');
  circle(g, 22, 13, 1, SOIL_DARK);
  // Mug handle
  px(g, 25, 12, TERRACOTTA);
  px(g, 25, 13, TERRACOTTA);
  px(g, 25, 14, TERRACOTTA);
  // Steam wisps
  px(g, 21, 9, STONE_LIGHT);
  px(g, 22, 8, STONE_LIGHT);
  px(g, 23, 9, STONE_LIGHT);
  px(g, 22, 7, '#d4c8b0');
  px(g, 21, 6, '#d4c8b0');
  // Small plant on left side of desk
  px(g, 7, 9, TERRACOTTA);
  px(g, 7, 8, 'AC');
  px(g, 8, 8, VINE_GREEN);
  // Golden drawer handle
  fill(g, 14, 18, 4, 1, SOLAR_GOLD);
  return g;
}

/** Desk with scattered paper documents */
function deskWithPapers() {
  const g = grid('FL');
  // Desk surface
  fill(g, 4, 6, 24, 16, 'FN');
  hline(g, 4, 6, 24, 'FH');
  hline(g, 4, 21, 24, 'FS');
  fill(g, 5, 22, 3, 4, 'FS');
  fill(g, 24, 22, 3, 4, 'FS');
  // Paper 1 (parchment-toned)
  fill(g, 7, 8, 5, 6, '#f0ebe0');
  fill(g, 7, 8, 5, 1, '#e0d8c8');
  hline(g, 8, 10, 3, STONE_WARM);
  hline(g, 8, 11, 3, STONE_WARM);
  // Paper 2 (warm cream)
  fill(g, 17, 10, 5, 7, '#f5f0e0');
  fill(g, 17, 10, 5, 1, '#e8e0c8');
  hline(g, 18, 12, 3, STONE_WARM);
  hline(g, 18, 13, 3, STONE_WARM);
  hline(g, 18, 14, 2, STONE_WARM);
  // Paper 3 (small)
  fill(g, 12, 14, 4, 5, '#f0ebe0');
  hline(g, 13, 16, 2, STONE_WARM);
  hline(g, 13, 17, 2, STONE_WARM);
  // Sticky note (solar gold)
  fill(g, 23, 8, 3, 3, SOLAR_GOLD);
  return g;
}

/** Monitor with visible code lines (active coding screen) */
function monitorActive() {
  const g = grid('FL');
  // Screen frame (warm wood bezel)
  rect(g, 5, 3, 22, 16, 'FN');
  hline(g, 6, 3, 20, 'FH');
  // Screen background (dark teal instead of cold blue)
  fill(g, 6, 4, 20, 14, '#0a1e2a');
  // Code lines — botanical color scheme
  hline(g, 8, 6, 6, CYAN_GLOW);
  hline(g, 15, 6, 4, '#f0ebe0');
  hline(g, 8, 8, 4, 'AC');
  hline(g, 13, 8, 8, LEAF_BRIGHT);
  hline(g, 10, 10, 10, '#f0ebe0');
  hline(g, 8, 12, 3, CYAN_GLOW);
  hline(g, 12, 12, 6, SOLAR_GOLD);
  hline(g, 10, 14, 8, LEAF_BRIGHT);
  hline(g, 8, 16, 5, 'AC');
  // Line numbers
  for (let r = 6; r <= 16; r += 2) {
    px(g, 7, r, '#4b5553');
  }
  // Stand (warm wood)
  fill(g, 13, 19, 6, 3, 'FN');
  fill(g, 10, 22, 12, 2, 'FN');
  hline(g, 10, 22, 12, 'FH');
  return g;
}

/** Monitor with video call (4 face squares) */
function monitorMeeting() {
  const g = grid('FL');
  // Screen frame (warm wood)
  rect(g, 5, 3, 22, 16, 'FN');
  hline(g, 6, 3, 20, 'FH');
  // Screen background
  fill(g, 6, 4, 20, 14, '#1a1a2e');
  // 4 video call squares (2x2 grid with warm backgrounds)
  fill(g, 7, 5, 8, 5, '#2a3a3a');
  circle(g, 11, 7, 1, '#e0b88a');
  px(g, 11, 6, BARK_MID);
  fill(g, 17, 5, 8, 5, '#2a4a3a');
  circle(g, 21, 7, 1, '#c4956a');
  px(g, 21, 6, '#1a1a2e');
  fill(g, 7, 11, 8, 5, '#3a2a3a');
  circle(g, 11, 13, 1, '#e0c8a0');
  px(g, 11, 12, TERRACOTTA);
  fill(g, 17, 11, 8, 5, '#1a3a3a');
  circle(g, 21, 13, 1, '#d4a574');
  px(g, 21, 12, '#374141');
  // Grid lines
  vline(g, 16, 5, 12, '#374141');
  hline(g, 7, 10, 18, '#374141');
  // Stand (warm wood)
  fill(g, 13, 19, 6, 3, 'FN');
  fill(g, 10, 22, 12, 2, 'FN');
  hline(g, 10, 22, 12, 'FH');
  return g;
}

/** Leather office chair with armrests */
function chairLeather() {
  const g = grid('FL');
  // Back rest (dark leather)
  fill(g, 9, 5, 14, 7, SOIL_DARK);
  fill(g, 9, 5, 14, 1, '#4a3828');
  // Leather tufting
  px(g, 12, 7, '#4a3828');
  px(g, 16, 7, '#4a3828');
  px(g, 20, 7, '#4a3828');
  px(g, 12, 9, '#4a3828');
  px(g, 16, 9, '#4a3828');
  px(g, 20, 9, '#4a3828');
  // Seat
  fill(g, 9, 12, 14, 12, '#4a3828');
  fill(g, 9, 12, 14, 2, '#5c4a32');
  fill(g, 9, 22, 14, 2, SOIL_DARK);
  // Armrests (warm wood)
  fill(g, 7, 8, 2, 14, 'FN');
  fill(g, 23, 8, 2, 14, 'FN');
  fill(g, 7, 8, 2, 1, 'FH');
  fill(g, 23, 8, 2, 1, 'FH');
  // Wheels
  px(g, 8, 25, '#374141');
  px(g, 23, 25, '#374141');
  px(g, 8, 11, '#374141');
  px(g, 23, 11, '#374141');
  fill(g, 15, 24, 2, 4, '#374141');
  return g;
}

/** Bookshelf with many colored book spines (FFVI library style) */
function bookshelfFull() {
  const g = grid('FL');
  // Shelf frame (warm wood)
  fill(g, 4, 2, 24, 28, 'FN');
  rect(g, 3, 1, 26, 30, 'FS');
  hline(g, 4, 1, 24, 'FH');
  // 4 shelves
  for (let r = 8; r < 28; r += 6) {
    hline(g, 4, r, 24, 'FH');
    hline(g, 4, r + 1, 24, 'FS');
  }
  // Books — botanical/earthy assortment
  const bookColors = [
    'AC', TERRACOTTA, MOSS_DARK, SOLAR_GOLD, '#7a4a3a', VINE_GREEN,
    '#8b6a4a', MOSS_LIGHT, '#6a3a3a', BARK_MID, '#4a6a5a', LEAF_BRIGHT,
  ];
  for (let shelf = 0; shelf < 4; shelf++) {
    const shelfY = 3 + shelf * 6;
    let bx = 5;
    for (let b = 0; b < 8 && bx < 26; b++) {
      const bw = (b % 3 === 0) ? 3 : 2;
      const bh = 4 + (b % 2);
      const color = bookColors[(shelf * 8 + b) % bookColors.length];
      fill(g, bx, shelfY + (5 - bh), bw, bh, color);
      if (bw >= 2) px(g, bx, shelfY + (5 - bh), 'FH');
      bx += bw + 1;
    }
  }
  // Trailing vine accent
  px(g, 5, 3, 'AC'); px(g, 6, 4, VINE_GREEN);
  px(g, 25, 9, 'AC'); px(g, 26, 10, VINE_GREEN);
  return g;
}

/** Flowering plant with pink/yellow blooms */
function plantFlowering() {
  const g = grid('FL');
  // Terracotta pot
  fill(g, 12, 22, 8, 6, TERRACOTTA);
  fill(g, 13, 21, 6, 1, STONE_WARM);
  hline(g, 12, 27, 8, BARK_MID);
  fill(g, 13, 22, 6, 2, SOIL_DARK);
  // Leaves (base)
  fill(g, 13, 14, 6, 8, 'AC');
  fill(g, 11, 16, 2, 4, 'AC');
  fill(g, 19, 16, 2, 4, 'AC');
  fill(g, 14, 12, 4, 2, VINE_GREEN);
  // Flower blooms (pink and golden)
  px(g, 14, 11, '#f472b6');
  px(g, 15, 10, '#f472b6');
  px(g, 17, 11, SOLAR_GOLD);
  px(g, 18, 10, SOLAR_GOLD);
  px(g, 11, 15, '#f472b6');
  px(g, 20, 15, SOLAR_GOLD);
  px(g, 16, 9, '#f472b6');
  px(g, 13, 13, SOLAR_GOLD);
  px(g, 19, 13, '#f472b6');
  // Leaf highlights
  px(g, 14, 15, LEAF_BRIGHT);
  px(g, 17, 17, LEAF_BRIGHT);
  return g;
}

/** Tall plant with varied greens and golden light */
function plantTall() {
  const g = grid('FL');
  // Large terracotta pot
  fill(g, 10, 24, 12, 6, TERRACOTTA);
  fill(g, 11, 23, 10, 1, STONE_WARM);
  hline(g, 10, 29, 12, BARK_MID);
  fill(g, 11, 24, 10, 2, SOIL_DARK);
  // Trunk (thick, warm bark)
  fill(g, 14, 16, 4, 8, BARK_MID);
  fill(g, 15, 16, 2, 8, '#5c3a1e');
  // Large canopy with varied greens
  circle(g, 16, 10, 9, MOSS_DARK);
  circle(g, 12, 8, 6, 'AC');
  circle(g, 20, 8, 6, 'AC');
  circle(g, 16, 6, 6, VINE_GREEN);
  circle(g, 14, 4, 4, LEAF_BRIGHT);
  circle(g, 18, 5, 3, LEAF_BRIGHT);
  // Golden sunlight highlights
  px(g, 10, 7, SOLAR_GOLD);
  px(g, 18, 4, SOLAR_GOLD);
  px(g, 22, 9, VINE_GREEN);
  px(g, 8, 10, 'AC');
  return g;
}

/** Southern shadow — warm-toned gradient */
function floorShadowS() {
  const g = grid('FL');
  for (let r = 0; r < 8; r++) {
    const darkness = 1 - (r / 8);
    if (darkness > 0.7) {
      hline(g, 0, r, 32, '#6a5838');
    } else if (darkness > 0.4) {
      hline(g, 0, r, 32, '#7a6848');
    } else {
      hline(g, 0, r, 32, '#826e4e');
    }
  }
  return g;
}

/** Eastern shadow — warm-toned gradient */
function floorShadowE() {
  const g = grid('FL');
  for (let c = 0; c < 8; c++) {
    const darkness = 1 - (c / 8);
    if (darkness > 0.7) {
      vline(g, c, 0, 32, '#6a5838');
    } else if (darkness > 0.4) {
      vline(g, c, 0, 32, '#7a6848');
    } else {
      vline(g, c, 0, 32, '#826e4e');
    }
  }
  return g;
}

/** Warm circular light pool on floor (golden sunbeam) */
function floorLightPool() {
  const g = grid('FL');
  for (let r = 0; r < 32; r++) {
    for (let c = 0; c < 32; c++) {
      const dx = c - 16;
      const dy = r - 16;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist <= 4) {
        g[r][c] = '#b8a878'; // bright golden center
      } else if (dist <= 8) {
        g[r][c] = '#a89868';
      } else if (dist <= 12) {
        g[r][c] = '#988860';
      }
    }
  }
  return g;
}

/** Amber-gold ceiling lamp with warm glow */
function ceilingLampWarm() {
  const g = grid('FL');
  // Warm glow halo (outer)
  for (let r = 0; r < 32; r++) {
    for (let c = 0; c < 32; c++) {
      const dx = c - 16;
      const dy = r - 16;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist >= 6 && dist <= 11) {
        g[r][c] = '#9a8a6a'; // subtle warm tint on floor
      }
    }
  }
  // Lamp fixture (golden/amber)
  circle(g, 16, 16, 6, '#d4a020');
  circle(g, 16, 16, 4, SOLAR_GOLD);
  circle(g, 16, 16, 2, '#fde68a');
  circle(g, 16, 16, 1, '#fffbe6');
  return g;
}

/** Small centered vent grate (bamboo-framed) */
function ventGrate() {
  const g = grid('FL');
  // Vent housing (warm wood frame)
  fill(g, 10, 10, 12, 12, 'WD');
  rect(g, 10, 10, 12, 12, 'FN');
  // Vent slats (horizontal)
  for (let r = 12; r < 20; r += 2) {
    hline(g, 12, r, 8, 'WH');
    hline(g, 12, r + 1, 8, 'WD');
  }
  // Corner screws (golden)
  px(g, 11, 11, SOLAR_GOLD);
  px(g, 20, 11, SOLAR_GOLD);
  px(g, 11, 20, SOLAR_GOLD);
  px(g, 20, 20, SOLAR_GOLD);
  return g;
}

/** Whiteboard with colored marker scribbles (wall decoration) */
function whiteboardScribbles() {
  const g = grid('WL');
  // Board frame on wall (warm wood)
  fill(g, 3, 4, 26, 22, 'FN');
  // Warm white surface
  fill(g, 4, 5, 24, 20, '#f0ebe0');
  // Colored marker lines (botanical palette)
  hline(g, 6, 8, 14, 'AC');
  px(g, 20, 7, 'AC');
  px(g, 8, 9, 'AC');
  hline(g, 6, 12, 16, TERRACOTTA);
  px(g, 7, 11, TERRACOTTA);
  px(g, 22, 13, TERRACOTTA);
  hline(g, 6, 16, 12, SOLAR_GOLD);
  px(g, 18, 15, SOLAR_GOLD);
  px(g, 9, 17, SOLAR_GOLD);
  hline(g, 8, 20, 10, MOSS_DARK);
  px(g, 18, 19, MOSS_DARK);
  // Marker tray
  fill(g, 6, 25, 20, 2, 'FS');
  fill(g, 8, 25, 3, 1, 'AC');
  fill(g, 12, 25, 3, 1, TERRACOTTA);
  fill(g, 16, 25, 3, 1, SOLAR_GOLD);
  return g;
}

/** 4 colored sticky notes (botanical tones) */
function stickyNotes() {
  const g = grid('FL');
  // Golden sticky (top-left)
  fill(g, 4, 4, 6, 6, SOLAR_GOLD);
  fill(g, 4, 4, 6, 1, '#e5a800');
  hline(g, 5, 6, 4, '#d4a020');
  hline(g, 5, 8, 3, '#d4a020');
  // Pink sticky (top-right)
  fill(g, 20, 3, 6, 6, '#f472b6');
  fill(g, 20, 3, 6, 1, '#e0559e');
  hline(g, 21, 5, 4, '#e0559e');
  hline(g, 21, 7, 3, '#e0559e');
  // Green sticky (bottom-left)
  fill(g, 6, 18, 6, 6, MOSS_LIGHT);
  fill(g, 6, 18, 6, 1, 'AC');
  hline(g, 7, 20, 4, 'AC');
  hline(g, 7, 22, 3, 'AC');
  // Terracotta sticky (bottom-right)
  fill(g, 22, 20, 6, 6, TERRACOTTA);
  fill(g, 22, 20, 6, 1, BARK_MID);
  hline(g, 23, 22, 4, BARK_MID);
  hline(g, 23, 24, 3, BARK_MID);
  return g;
}

/** Coffee machine v2 (FFVI-quality, warm wood body) */
function coffeeMachineV2() {
  const g = grid('FL');
  // Machine body (warm wood)
  fill(g, 8, 4, 16, 22, 'FN');
  fill(g, 8, 4, 16, 1, 'FH');
  vline(g, 8, 4, 22, 'FH');
  vline(g, 23, 4, 22, 'FS');
  hline(g, 8, 25, 16, 'FS');
  // Top hopper
  fill(g, 10, 2, 12, 3, 'FS');
  fill(g, 11, 2, 10, 1, 'FN');
  // Display panel (green LED)
  fill(g, 11, 6, 10, 4, '#1a2e1a');
  fill(g, 12, 7, 8, 2, 'AC');
  // Buttons
  px(g, 12, 11, TERRACOTTA);
  px(g, 14, 11, 'AC');
  px(g, 16, 11, CYAN_GLOW);
  // Drip spout
  fill(g, 14, 13, 4, 2, '#374141');
  fill(g, 15, 15, 2, 1, '#374141');
  // Drip drops
  px(g, 16, 16, TERRACOTTA);
  px(g, 15, 17, BARK_MID);
  // Ceramic cup
  fill(g, 13, 18, 6, 4, '#f0ebe0');
  fill(g, 12, 18, 1, 4, STONE_WARM);
  fill(g, 14, 19, 4, 1, TERRACOTTA);
  // Steam
  px(g, 14, 16, STONE_LIGHT);
  px(g, 17, 15, STONE_LIGHT);
  // Base
  fill(g, 10, 26, 12, 2, 'FS');
  return g;
}

/** Server rack with blinking LEDs (warm wood frame) */
function serverRackActive() {
  const g = grid('FL');
  // Rack body (dark tech with warm wood frame)
  fill(g, 4, 2, 24, 28, '#2d2d2e');
  rect(g, 3, 1, 26, 30, 'FN');
  hline(g, 4, 1, 24, 'FH');
  // Server units (5 bays)
  for (let i = 0; i < 5; i++) {
    const sy = 3 + i * 5;
    fill(g, 6, sy, 20, 4, '#374141');
    hline(g, 6, sy, 20, '#4b5553');
    for (let c = 8; c < 20; c += 3) {
      px(g, c, sy + 2, '#1f2927');
    }
  }
  // LED indicators — green (healthy), gold (active)
  px(g, 22, 4, 'AC');
  px(g, 24, 4, 'AC');
  px(g, 22, 9, SOLAR_GOLD);
  px(g, 24, 9, TERRACOTTA);
  px(g, 22, 14, 'AC');
  px(g, 24, 14, 'AC');
  px(g, 22, 19, 'AC');
  px(g, 24, 19, SOLAR_GOLD);
  px(g, 22, 24, 'AC');
  px(g, 24, 24, 'AC');
  // Activity lights (cyan tech glow)
  px(g, 7, 5, CYAN_GLOW);
  px(g, 7, 15, CYAN_GLOW);
  px(g, 7, 25, CYAN_GLOW);
  return g;
}

/** Award plaque — warm gold on bamboo wall */
function awardPlaque() {
  const g = grid('WL');
  // Plaque frame (warm wood)
  fill(g, 10, 8, 12, 16, 'FN');
  rect(g, 10, 8, 12, 16, 'FS');
  // Inner plaque (golden)
  fill(g, 12, 10, 8, 12, SOLAR_GOLD);
  fill(g, 12, 10, 8, 1, '#fde68a');
  // Engraving lines
  hline(g, 13, 13, 6, '#d4a020');
  hline(g, 14, 15, 4, '#d4a020');
  hline(g, 13, 17, 6, '#d4a020');
  // Star at top
  px(g, 16, 11, '#fffbe6');
  px(g, 15, 12, '#fde68a');
  px(g, 17, 12, '#fde68a');
  // Mounting bracket
  px(g, 16, 7, 'FS');
  // Tiny vine accent
  px(g, 22, 18, 'AC'); px(g, 22, 19, VINE_GREEN);
  return g;
}

/** Clock face on wall — warm wood rim */
function clockFace() {
  const g = grid('WL');
  // Clock body (warm wood frame)
  circle(g, 16, 14, 8, 'FN');
  circle(g, 16, 14, 7, '#f0ebe0');
  circle(g, 16, 14, 6, '#f8f4ea');
  // Hour markers
  px(g, 16, 8, 'FS'); px(g, 16, 9, 'FS');
  px(g, 22, 14, 'FS'); px(g, 21, 14, 'FS');
  px(g, 16, 20, 'FS'); px(g, 16, 19, 'FS');
  px(g, 10, 14, 'FS'); px(g, 11, 14, 'FS');
  // Minor markers
  px(g, 19, 9, STONE_WARM);
  px(g, 21, 11, STONE_WARM);
  px(g, 21, 17, STONE_WARM);
  px(g, 19, 19, STONE_WARM);
  px(g, 13, 19, STONE_WARM);
  px(g, 11, 17, STONE_WARM);
  px(g, 11, 11, STONE_WARM);
  px(g, 13, 9, STONE_WARM);
  // Hour hand
  vline(g, 16, 10, 4, 'FS');
  px(g, 15, 11, 'FS');
  // Minute hand
  hline(g, 16, 14, 4, TERRACOTTA);
  px(g, 19, 13, TERRACOTTA);
  // Center dot (golden)
  px(g, 16, 14, SOLAR_GOLD);
  // Frame ring
  circle(g, 16, 14, 8, 'FN');
  circle(g, 16, 14, 7, '#f0ebe0');
  circle(g, 16, 14, 6, '#f8f4ea');
  // Re-draw markers and hands
  px(g, 16, 8, 'FS'); px(g, 22, 14, 'FS');
  px(g, 16, 20, 'FS'); px(g, 10, 14, 'FS');
  vline(g, 16, 10, 4, 'FS');
  hline(g, 16, 14, 4, TERRACOTTA);
  px(g, 16, 14, SOLAR_GOLD);
  return g;
}

/** Wall with decorative molding — bamboo panel with vine crown molding */
function wallMoldingTop() {
  const g = grid('WL');
  fill(g, 0, 0, 32, 3, 'WD');
  // Bamboo stalks
  for (let c = 3; c < 32; c += 4) {
    vline(g, c, 3, 23, 'WD');
    if (c - 1 >= 0) vline(g, c - 1, 3, 23, 'WH');
  }
  // Decorative vine molding at bottom
  fill(g, 0, 27, 32, 2, 'AC');
  hline(g, 0, 26, 32, VINE_GREEN);
  hline(g, 0, 29, 32, MOSS_DARK);
  // Vine leaf accents
  for (let c = 0; c < 32; c += 4) {
    px(g, c, 27, MOSS_LIGHT);
    px(g, c + 2, 28, LEAF_BRIGHT);
  }
  fill(g, 0, 30, 32, 2, 'WD');
  return g;
}

/** Wall tile with warm wood baseboard */
function wallBaseboard() {
  const g = grid('WL');
  // Baseboard (warm wood)
  fill(g, 0, 0, 32, 3, 'FN');
  hline(g, 0, 0, 32, 'FH');
  hline(g, 0, 3, 32, 'FS');
  // Standard bamboo wall detail below
  for (let c = 3; c < 32; c += 4) {
    vline(g, c, 4, 24, 'WD');
    if (c - 1 >= 0) vline(g, c - 1, 4, 24, 'WH');
  }
  fill(g, 0, 29, 32, 3, 'WD');
  return g;
}

/** Window (daytime view) — warm wood frame with lush greenery outside */
function windowDay() {
  const g = grid('WL');
  // Window frame (warm wood outer)
  fill(g, 4, 2, 24, 26, 'FS');
  fill(g, 5, 3, 22, 24, 'FN');
  // Sky (light cyan)
  fill(g, 6, 4, 20, 22, SKY_BLUE);
  // Clouds
  fill(g, 8, 7, 6, 2, '#e0f0ff');
  fill(g, 9, 6, 4, 1, '#e0f0ff');
  fill(g, 18, 9, 5, 2, '#e0f0ff');
  // Trees/greenery outside (solarpunk cityscape with gardens)
  fill(g, 7, 16, 4, 10, MOSS_DARK);
  fill(g, 8, 14, 3, 2, VINE_GREEN);
  fill(g, 12, 18, 3, 8, 'AC');
  fill(g, 13, 16, 2, 2, LEAF_BRIGHT);
  fill(g, 16, 14, 5, 12, MOSS_DARK);
  fill(g, 17, 12, 3, 2, VINE_GREEN);
  fill(g, 22, 17, 3, 9, 'AC');
  fill(g, 23, 15, 2, 2, LEAF_BRIGHT);
  // Solar panel glints on distant rooftops
  px(g, 8, 18, SOLAR_GOLD);
  px(g, 17, 16, SOLAR_GOLD);
  px(g, 23, 19, SOLAR_GOLD);
  // Cross-bars (warm wood)
  vline(g, 16, 4, 22, 'FN');
  hline(g, 6, 14, 20, 'FN');
  // Frame highlight
  hline(g, 5, 3, 22, 'FH');
  vline(g, 5, 3, 24, 'FH');
  return g;
}

/** Structural column/pillar — warm bamboo/sandstone */
function pillar() {
  const g = grid('FL');
  // Column body (sandstone with warm tones)
  fill(g, 10, 0, 12, 32, 'WL');
  // Highlight (left face)
  vline(g, 10, 0, 32, 'WH');
  vline(g, 11, 0, 32, 'WH');
  // Shadow (right face)
  vline(g, 21, 0, 32, 'WD');
  vline(g, 20, 0, 32, 'WD');
  // Capital (top decorative band with green accent)
  fill(g, 9, 0, 14, 3, 'WH');
  hline(g, 9, 2, 14, 'WD');
  hline(g, 9, 0, 14, 'AC'); // moss line at top
  // Base (bottom decorative band with green accent)
  fill(g, 9, 29, 14, 3, 'WH');
  hline(g, 9, 29, 14, 'WD');
  hline(g, 9, 31, 14, 'AC'); // moss line at bottom
  return g;
}

/** Circular rug — green/gold concentric rings */
function rugRoundV2() {
  const g = grid('FL');
  // Outer ring (green)
  circle(g, 16, 16, 13, 'AC');
  // Dark ring
  circle(g, 16, 16, 11, MOSS_DARK);
  // Middle ring
  circle(g, 16, 16, 9, 'AC');
  // Inner dark
  circle(g, 16, 16, 7, MOSS_DARK);
  // Center
  circle(g, 16, 16, 5, 'AC');
  // Decorative golden dots on middle ring
  for (let a = 0; a < 8; a++) {
    const angle = (a / 8) * Math.PI * 2;
    const rx = Math.round(16 + Math.cos(angle) * 10);
    const ry = Math.round(16 + Math.sin(angle) * 10);
    px(g, rx, ry, SOLAR_GOLD);
  }
  return g;
}

// ---------------------------------------------------------------------------
// Tile order and export
// ---------------------------------------------------------------------------

const TILE_ORDER = [
  // Original 8 (indices 0-7)
  'floor', 'wall', 'desk',
  'dept_engineering', 'dept_sales', 'dept_support', 'dept_research',
  'review_station',
  // Walls (indices 8-19)
  'wall_top', 'wall_bottom', 'wall_left', 'wall_right',
  'wall_corner_tl', 'wall_corner_tr', 'wall_corner_bl', 'wall_corner_br',
  'wall_inner_tl', 'wall_inner_tr', 'wall_inner_bl', 'wall_inner_br',
  // Floors (indices 20-27)
  'floor_corridor', 'floor_lobby',
  'floor_carpet_blue', 'floor_carpet_purple', 'floor_carpet_green',
  'floor_carpet_brown', 'floor_carpet_indigo', 'floor_grid',
  // Furniture (indices 28-42)
  'desk_front', 'desk_side', 'chair', 'monitor', 'monitor_on',
  'bookshelf', 'plant_small', 'plant_large', 'whiteboard',
  'water_cooler', 'coffee_machine', 'filing_cabinet', 'server_rack',
  'printer', 'couch',
  // Stations (indices 43-45)
  'review_station_v2', 'dispatch_terminal', 'blueprint_table',
  // Decorations (indices 46-53)
  'rug_round', 'poster_a', 'poster_b', 'clock', 'ceiling_light',
  'door_h', 'door_v', 'welcome_mat',
  // FFVI-quality tiles (indices 54-78)
  'desk_wood', 'desk_with_coffee', 'desk_with_papers',
  'monitor_active', 'monitor_meeting',
  'chair_leather', 'bookshelf_full',
  'plant_flowering', 'plant_tall',
  'floor_shadow_s', 'floor_shadow_e', 'floor_light_pool',
  'ceiling_lamp_warm', 'vent_grate',
  'whiteboard_scribbles', 'sticky_notes',
  'coffee_machine_v2', 'server_rack_active',
  'award_plaque', 'clock_face',
  'wall_molding_top', 'wall_baseboard',
  'window_day', 'pillar', 'rug_round_v2',
];

const TILE_COLUMNS = 16; // 16 columns; 79 tiles = 5 rows = 512x160 PNG

/** Tile name → generator function mapping for all tiles */
const TILE_GENERATORS = {
  // Original 8 tiles (now generated, override tiles.json)
  floor: floorBase,
  wall: wallBase,
  desk: deskBase,
  dept_engineering: deptEngineering,
  dept_sales: deptSales,
  dept_support: deptSupport,
  dept_research: deptResearch,
  review_station: reviewStation,
  // Walls
  wall_top: wallTop,
  wall_bottom: wallBottom,
  wall_left: wallLeft,
  wall_right: wallRight,
  wall_corner_tl: wallCornerTL,
  wall_corner_tr: wallCornerTR,
  wall_corner_bl: wallCornerBL,
  wall_corner_br: wallCornerBR,
  wall_inner_tl: wallInnerTL,
  wall_inner_tr: wallInnerTR,
  wall_inner_bl: wallInnerBL,
  wall_inner_br: wallInnerBR,
  // Floors
  floor_corridor: floorCorridor,
  floor_lobby: floorLobby,
  floor_carpet_blue: () => floorCarpet('CE'),
  floor_carpet_purple: () => floorCarpet('CS'),
  floor_carpet_green: () => floorCarpet('CU'),
  floor_carpet_brown: () => floorCarpet('CR'),
  floor_carpet_indigo: () => floorCarpet('CB'),
  floor_grid: floorGrid,
  // Furniture
  desk_front: deskFront,
  desk_side: deskSide,
  chair: chair,
  monitor: monitor,
  monitor_on: monitorOn,
  bookshelf: bookshelf,
  plant_small: plantSmall,
  plant_large: plantLarge,
  whiteboard: whiteboard,
  water_cooler: waterCooler,
  coffee_machine: coffeeMachine,
  filing_cabinet: filingCabinet,
  server_rack: serverRack,
  printer: printer,
  couch: couch,
  // Stations
  review_station_v2: reviewStationV2,
  dispatch_terminal: dispatchTerminal,
  blueprint_table: blueprintTable,
  // Decorations
  rug_round: rugRound,
  poster_a: posterA,
  poster_b: posterB,
  clock: clock,
  ceiling_light: ceilingLight,
  door_h: doorH,
  door_v: doorV,
  welcome_mat: welcomeMat,
  // FFVI-quality tiles
  desk_wood: deskWood,
  desk_with_coffee: deskWithCoffee,
  desk_with_papers: deskWithPapers,
  monitor_active: monitorActive,
  monitor_meeting: monitorMeeting,
  chair_leather: chairLeather,
  bookshelf_full: bookshelfFull,
  plant_flowering: plantFlowering,
  plant_tall: plantTall,
  floor_shadow_s: floorShadowS,
  floor_shadow_e: floorShadowE,
  floor_light_pool: floorLightPool,
  ceiling_lamp_warm: ceilingLampWarm,
  vent_grate: ventGrate,
  whiteboard_scribbles: whiteboardScribbles,
  sticky_notes: stickyNotes,
  coffee_machine_v2: coffeeMachineV2,
  server_rack_active: serverRackActive,
  award_plaque: awardPlaque,
  clock_face: clockFace,
  wall_molding_top: wallMoldingTop,
  wall_baseboard: wallBaseboard,
  window_day: windowDay,
  pillar: pillar,
  rug_round_v2: rugRoundV2,
};

/**
 * Build the default environment color map for resolving palette tokens.
 * Solarpunk palette: warm wood, bamboo, living greenery.
 */
function buildDefaultEnvColorMap() {
  return {
    FL: '#8b7355',   // floor base — warm wood plank
    FD: '#6b5a42',   // floor dark (wood shadow)
    WL: '#c8b896',   // wall face — bamboo/sandstone
    WD: '#a89878',   // wall dark/shadow
    WH: '#e8dcc4',   // wall highlight — sunlit bamboo
    FN: '#6b5a42',   // furniture base — dark wood
    FH: '#d4b896',   // furniture highlight — polished wood
    FS: '#4a3a2a',   // furniture shadow — deep shadow
    AC: '#4a9e6e',   // accent — living green
    DP: '#8b7355',   // door — warm wood
    CE: '#2d5a4a',   // carpet engineering — tech-garden teal
    CS: '#6b5a2a',   // carpet sales — market-garden gold
    CU: '#3a5a3a',   // carpet support — zen-garden green
    CR: '#2a4a5a',   // carpet research — library-garden ocean
    CB: '#5a4a3a',   // carpet blueprint — warm wood
  };
}

/**
 * Build an environment color map from a palette preset.
 */
function buildEnvColorMap(presetEnv) {
  function darken(hex, factor) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `#${Math.round(r * (1 - factor)).toString(16).padStart(2, '0')}${Math.round(g * (1 - factor)).toString(16).padStart(2, '0')}${Math.round(b * (1 - factor)).toString(16).padStart(2, '0')}`;
  }
  function lighten(hex, factor) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `#${Math.round(r + (255 - r) * factor).toString(16).padStart(2, '0')}${Math.round(g + (255 - g) * factor).toString(16).padStart(2, '0')}${Math.round(b + (255 - b) * factor).toString(16).padStart(2, '0')}`;
  }

  const floor = presetEnv.floor || '#8b7355';
  const wall = presetEnv.wall || '#c8b896';
  const furnitureBase = presetEnv.furnitureBase || darken(wall, 0.3);
  const furnitureHighlight = presetEnv.furnitureHighlight || lighten(furnitureBase, 0.35);

  return {
    FL: floor,
    FD: darken(floor, 0.25),
    WL: wall,
    WD: darken(wall, 0.2),
    WH: lighten(wall, 0.15),
    FN: furnitureBase,
    FH: furnitureHighlight,
    FS: darken(furnitureBase, 0.25),
    AC: presetEnv.accent || presetEnv.reviewStation || '#4a9e6e',
    DP: floor,
    CE: presetEnv.carpetEngineering || presetEnv.deptEngineering || '#2d5a4a',
    CS: presetEnv.carpetSales || presetEnv.deptSales || '#6b5a2a',
    CU: presetEnv.carpetSupport || presetEnv.deptSupport || '#3a5a3a',
    CR: presetEnv.carpetResearch || presetEnv.deptResearch || '#2a4a5a',
    CB: presetEnv.carpetBlueprint || '#5a4a3a',
  };
}

/**
 * Get all 79 tile grids in order.
 * Generators take priority over tiles.json for full theme-ability.
 */
function getAllTiles() {
  const tiles = {};

  for (const name of TILE_ORDER) {
    if (TILE_GENERATORS[name]) {
      // Generate programmatically (preferred — uses palette tokens)
      tiles[name] = TILE_GENERATORS[name]();
    } else if (tileTemplates[name]) {
      // Fallback to tiles.json
      tiles[name] = tileTemplates[name];
    } else {
      console.warn(`  warning: no tile data for "${name}"`);
      tiles[name] = grid('FL');
    }
  }

  return tiles;
}

module.exports = {
  getAllTiles,
  buildDefaultEnvColorMap,
  buildEnvColorMap,
  TILE_ORDER,
  TILE_COLUMNS,
  TILE_GENERATORS,
};
