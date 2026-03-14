/**
 * tile-definitions.js
 *
 * Programmatically generates all 54 tile grids (32x32) for the office tileset.
 * Original 8 tiles are loaded from tiles.json; 46 new tiles are generated here
 * using palette tokens (FL, WL, WH, etc.) for theme-ability via palette presets.
 *
 * Tile index layout: 16 columns x 4 rows = 512x128 PNG
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
// Wall tiles (12) — indices 8-19
// ---------------------------------------------------------------------------

/** Wall at top of room — face/highlight on bottom edge */
function wallTop() {
  const g = grid('WL');
  // Top shadow edge
  fill(g, 0, 0, 32, 3, 'WD');
  // Horizontal detail line
  hline(g, 0, 10, 32, 'WD');
  hline(g, 0, 11, 32, 'WD');
  // Bottom face (highlight, facing room below)
  fill(g, 0, 26, 32, 3, 'WH');
  // Panel details — vertical lines every 8px
  for (let c = 7; c < 32; c += 8) {
    vline(g, c, 12, 14, 'WD');
  }
  // Baseboard
  fill(g, 0, 29, 32, 3, 'WD');
  return g;
}

/** Wall at bottom of room — face/highlight on top edge */
function wallBottom() {
  const g = grid('WL');
  // Top face (highlight, facing room above)
  fill(g, 0, 0, 32, 3, 'WH');
  // Horizontal detail
  hline(g, 0, 18, 32, 'WD');
  hline(g, 0, 19, 32, 'WD');
  // Panel verticals
  for (let c = 7; c < 32; c += 8) {
    vline(g, c, 3, 15, 'WD');
  }
  // Bottom shadow
  fill(g, 0, 29, 32, 3, 'WD');
  return g;
}

/** Wall at left of room — face/highlight on right edge */
function wallLeft() {
  const g = grid('WL');
  // Left shadow
  fill(g, 0, 0, 3, 32, 'WD');
  // Right face (highlight, facing room)
  fill(g, 26, 0, 3, 32, 'WH');
  // Horizontal detail lines
  for (let r = 7; r < 32; r += 8) {
    hline(g, 3, r, 23, 'WD');
  }
  // Baseboard right
  fill(g, 29, 0, 3, 32, 'WD');
  return g;
}

/** Wall at right of room — face/highlight on left edge */
function wallRight() {
  const g = grid('WL');
  // Right shadow
  fill(g, 29, 0, 3, 32, 'WD');
  // Left face (highlight)
  fill(g, 3, 0, 3, 32, 'WH');
  // Horizontal detail lines
  for (let r = 7; r < 32; r += 8) {
    hline(g, 6, r, 23, 'WD');
  }
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
  // Corner detail
  fill(g, 26, 26, 6, 6, 'WH');
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
  return g;
}

/** Inner corner: top-left (concave, wall fills TL quadrant) */
function wallInnerTL() {
  const g = grid('FL');
  // Wall fills top-left quadrant
  fill(g, 0, 0, 16, 16, 'WL');
  fill(g, 0, 0, 16, 2, 'WD');
  fill(g, 0, 0, 2, 16, 'WD');
  // Highlight edges facing room
  hline(g, 0, 15, 16, 'WH');
  vline(g, 15, 0, 16, 'WH');
  // Wall extends along top
  fill(g, 16, 0, 16, 3, 'WL');
  fill(g, 16, 0, 16, 1, 'WD');
  hline(g, 16, 2, 16, 'WH');
  // Wall extends along left
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
  fill(g, 29, 0, 3, 16, 'WL');
  vline(g, 31, 0, 16, 'WD');
  vline(g, 29, 0, 16, 'WH');
  fill(g, 0, 29, 16, 3, 'WL');
  hline(g, 0, 29, 16, 'WH');
  fill(g, 0, 31, 16, 1, 'WD');
  return g;
}

// ---------------------------------------------------------------------------
// Floor tiles (8) — indices 20-27
// ---------------------------------------------------------------------------

/** Corridor floor — lighter with subtle line pattern every 8px */
function floorCorridor() {
  const g = grid('FL');
  for (let r = 0; r < 32; r += 8) {
    hline(g, 0, r, 32, 'FD');
  }
  for (let c = 0; c < 32; c += 8) {
    vline(g, c, 0, 32, 'FD');
  }
  return g;
}

/** Lobby floor — diamond checkerboard pattern */
function floorLobby() {
  const g = grid('FL');
  diamonds(g, 0, 0, 32, 32, 'FL', 'FD', 8);
  return g;
}

/** Department carpet with border trim */
function floorCarpet(token) {
  const g = grid(token);
  // Border trim (darker edge)
  rect(g, 0, 0, 32, 32, 'FD');
  rect(g, 1, 1, 30, 30, 'FD');
  // Subtle inner pattern
  for (let r = 4; r < 28; r += 4) {
    for (let c = 4; c < 28; c += 4) {
      px(g, c, r, 'FD');
    }
  }
  return g;
}

/** Grid floor — subtle grid lines */
function floorGrid() {
  const g = grid('FL');
  gridPattern(g, 0, 0, 32, 32, 'FL', 'FD', 4);
  return g;
}

// ---------------------------------------------------------------------------
// Furniture tiles (15) — indices 28-42
// ---------------------------------------------------------------------------

/** Desk viewed from front (top-down, facing south) */
function deskFront() {
  const g = grid('FL');
  // Desk surface
  fill(g, 4, 6, 24, 16, 'FN');
  // Highlight top edge
  hline(g, 4, 6, 24, 'FH');
  // Shadow bottom
  hline(g, 4, 21, 24, 'FS');
  // Legs
  fill(g, 5, 22, 3, 4, 'FS');
  fill(g, 24, 22, 3, 4, 'FS');
  // Drawer handle
  fill(g, 14, 18, 4, 1, 'FH');
  return g;
}

/** Desk viewed from side */
function deskSide() {
  const g = grid('FL');
  fill(g, 8, 6, 16, 14, 'FN');
  hline(g, 8, 6, 16, 'FH');
  vline(g, 8, 6, 14, 'FH');
  hline(g, 8, 19, 16, 'FS');
  vline(g, 23, 6, 14, 'FS');
  // Legs
  fill(g, 9, 20, 2, 6, 'FS');
  fill(g, 21, 20, 2, 6, 'FS');
  return g;
}

/** Chair from above */
function chair() {
  const g = grid('FL');
  // Seat
  fill(g, 10, 12, 12, 12, 'FN');
  fill(g, 10, 12, 12, 2, 'FH'); // highlight
  fill(g, 10, 22, 12, 2, 'FS'); // shadow
  // Back rest
  fill(g, 10, 6, 12, 6, 'FS');
  fill(g, 10, 6, 12, 1, 'FN');
  // Wheels (tiny dots)
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
  // Bezel highlight
  hline(g, 6, 3, 20, 'FH');
  // Stand
  fill(g, 13, 19, 6, 3, 'FS');
  fill(g, 10, 22, 12, 2, 'FS');
  hline(g, 10, 22, 12, 'FN');
  return g;
}

/** Monitor (on — cyan screen) */
function monitorOn() {
  const g = grid('FL');
  // Screen (lit)
  fill(g, 6, 4, 20, 14, '#0e4166');
  fill(g, 8, 6, 16, 10, 'AC');
  // Text lines on screen
  for (let r = 7; r < 15; r += 2) {
    hline(g, 9, r, 8 + (r % 4), '#0e4166');
  }
  rect(g, 5, 3, 22, 16, 'FS');
  hline(g, 6, 3, 20, 'FH');
  // Stand
  fill(g, 13, 19, 6, 3, 'FS');
  fill(g, 10, 22, 12, 2, 'FS');
  hline(g, 10, 22, 12, 'FN');
  return g;
}

/** Bookshelf (tall, viewed from front) */
function bookshelf() {
  const g = grid('FL');
  // Shelf frame
  fill(g, 4, 2, 24, 28, 'FN');
  rect(g, 3, 1, 26, 30, 'FS');
  hline(g, 4, 1, 24, 'FH');
  // Shelves (horizontal dividers)
  for (let r = 8; r < 28; r += 7) {
    hline(g, 4, r, 24, 'FH');
    hline(g, 4, r + 1, 24, 'FS');
  }
  // Books (colored spines on each shelf)
  const bookColors = ['#4a6fa5', '#c75c5c', '#5ca55c', '#c7a55c', '#8b5cc7', '#c75c8b'];
  for (let shelf = 0; shelf < 3; shelf++) {
    const shelfY = 3 + shelf * 7;
    for (let b = 0; b < 6; b++) {
      const bx = 6 + b * 3;
      fill(g, bx, shelfY, 2, 5, bookColors[(shelf * 6 + b) % bookColors.length]);
    }
  }
  return g;
}

/** Small potted plant */
function plantSmall() {
  const g = grid('FL');
  // Pot
  fill(g, 12, 22, 8, 6, '#8b5e3c');
  fill(g, 13, 21, 6, 1, '#a0704e');
  hline(g, 12, 27, 8, '#6b4226');
  // Soil
  fill(g, 13, 22, 6, 2, '#3d2b1f');
  // Leaves
  fill(g, 13, 14, 6, 8, '#2d8a4e');
  fill(g, 11, 16, 2, 4, '#2d8a4e');
  fill(g, 19, 16, 2, 4, '#2d8a4e');
  fill(g, 14, 12, 4, 2, '#3aad62');
  px(g, 15, 11, '#3aad62');
  px(g, 16, 11, '#3aad62');
  // Highlights
  px(g, 14, 15, '#4dcc73');
  px(g, 17, 17, '#4dcc73');
  return g;
}

/** Large plant / small tree */
function plantLarge() {
  const g = grid('FL');
  // Pot
  fill(g, 10, 24, 12, 6, '#8b5e3c');
  fill(g, 11, 23, 10, 1, '#a0704e');
  hline(g, 10, 29, 12, '#6b4226');
  fill(g, 11, 24, 10, 2, '#3d2b1f');
  // Trunk
  fill(g, 14, 18, 4, 6, '#6b4226');
  // Canopy
  circle(g, 16, 12, 8, '#2d8a4e');
  circle(g, 13, 10, 5, '#3aad62');
  circle(g, 19, 10, 5, '#3aad62');
  circle(g, 16, 8, 5, '#4dcc73');
  return g;
}

/** Whiteboard */
function whiteboard() {
  const g = grid('FL');
  // Board frame
  fill(g, 3, 3, 26, 20, 'FS');
  // White surface
  fill(g, 4, 4, 24, 18, '#e8e8e8');
  // Marker scribbles
  hline(g, 6, 7, 12, '#3b82f6');
  hline(g, 6, 9, 16, '#3b82f6');
  hline(g, 6, 12, 10, '#ef4444');
  hline(g, 6, 14, 14, '#ef4444');
  hline(g, 6, 17, 8, '#10b981');
  // Marker tray
  fill(g, 6, 23, 20, 2, 'FS');
  fill(g, 8, 23, 3, 1, '#3b82f6');
  fill(g, 12, 23, 3, 1, '#ef4444');
  fill(g, 16, 23, 3, 1, '#10b981');
  return g;
}

/** Water cooler */
function waterCooler() {
  const g = grid('FL');
  // Water jug (top)
  fill(g, 12, 2, 8, 10, '#bfdbfe');
  fill(g, 13, 1, 6, 1, '#93c5fd');
  fill(g, 14, 0, 4, 1, '#60a5fa');
  // Water level
  fill(g, 12, 6, 8, 6, '#3b82f6');
  // Body
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

/** Coffee machine */
function coffeeMachine() {
  const g = grid('FL');
  // Body
  fill(g, 8, 6, 16, 20, 'FN');
  fill(g, 8, 6, 16, 1, 'FH');
  vline(g, 8, 6, 20, 'FH');
  vline(g, 23, 6, 20, 'FS');
  hline(g, 8, 25, 16, 'FS');
  // Display
  fill(g, 11, 8, 10, 4, '#1a1a2e');
  fill(g, 12, 9, 8, 2, '#22c55e');
  // Brew area
  fill(g, 11, 14, 10, 6, '#1a1a2e');
  // Cup
  fill(g, 13, 17, 6, 3, '#e8e8e8');
  fill(g, 12, 17, 1, 3, '#d4d4d8');
  // Steam
  px(g, 15, 14, '#94a3b8');
  px(g, 16, 13, '#94a3b8');
  px(g, 17, 14, '#94a3b8');
  // Base
  fill(g, 10, 26, 12, 2, 'FS');
  return g;
}

/** Filing cabinet */
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
    // Handle
    fill(g, 14, dy + 2, 4, 2, 'FH');
  }
  return g;
}

/** Server rack */
function serverRack() {
  const g = grid('FL');
  // Rack body
  fill(g, 4, 2, 24, 28, '#2d2d3e');
  rect(g, 3, 1, 26, 30, '#1a1a2e');
  // Server units
  for (let i = 0; i < 5; i++) {
    const sy = 3 + i * 5;
    fill(g, 6, sy, 20, 4, '#374151');
    hline(g, 6, sy, 20, '#4b5563');
    // Vent holes
    for (let c = 8; c < 20; c += 3) {
      px(g, c, sy + 2, '#1f2937');
    }
    // LED indicators
    px(g, 22, sy + 1, '#22c55e');
    px(g, 24, sy + 1, '#f59e0b');
  }
  return g;
}

/** Printer */
function printer() {
  const g = grid('FL');
  // Body
  fill(g, 6, 10, 20, 14, 'FN');
  fill(g, 6, 10, 20, 1, 'FH');
  vline(g, 6, 10, 14, 'FH');
  vline(g, 25, 10, 14, 'FS');
  hline(g, 6, 23, 20, 'FS');
  // Paper tray top
  fill(g, 8, 6, 16, 4, 'FN');
  fill(g, 9, 6, 14, 2, '#e8e8e8');
  // Output tray
  fill(g, 10, 24, 12, 3, 'FN');
  fill(g, 11, 24, 10, 2, '#e8e8e8');
  // Display
  fill(g, 9, 13, 6, 3, '#1a1a2e');
  fill(g, 10, 14, 4, 1, '#22c55e');
  // Buttons
  px(g, 18, 14, '#3b82f6');
  px(g, 20, 14, '#ef4444');
  return g;
}

/** Couch (2-seater from above) */
function couch() {
  const g = grid('FL');
  // Backrest
  fill(g, 4, 4, 24, 8, 'FN');
  hline(g, 4, 4, 24, 'FH');
  fill(g, 4, 4, 24, 2, 'FH');
  // Seat cushions
  fill(g, 4, 12, 24, 12, 'FN');
  // Cushion divider
  vline(g, 16, 12, 12, 'FS');
  // Highlight
  hline(g, 4, 12, 24, 'FH');
  // Armrests
  fill(g, 2, 6, 2, 18, 'FS');
  fill(g, 28, 6, 2, 18, 'FS');
  // Shadow
  hline(g, 4, 23, 24, 'FS');
  fill(g, 2, 24, 2, 4, 'FS');
  fill(g, 28, 24, 2, 4, 'FS');
  return g;
}

// ---------------------------------------------------------------------------
// Station tiles (3) — indices 43-45
// ---------------------------------------------------------------------------

/** Review station v2 — pedestal with holographic display */
function reviewStationV2() {
  const g = grid('FL');
  // Pedestal base
  circle(g, 16, 22, 8, 'FS');
  circle(g, 16, 22, 6, 'FN');
  circle(g, 16, 22, 4, 'FH');
  // Column
  fill(g, 14, 12, 4, 10, 'FN');
  vline(g, 14, 12, 10, 'FH');
  vline(g, 17, 12, 10, 'FS');
  // Holographic display (amber/gold glow)
  fill(g, 8, 4, 16, 8, '#fbbf2440');
  fill(g, 10, 5, 12, 6, '#fbbf24');
  fill(g, 11, 6, 10, 4, '#fde68a');
  // Approval icon
  px(g, 14, 7, '#ffffff');
  px(g, 15, 8, '#ffffff');
  px(g, 16, 7, '#ffffff');
  px(g, 17, 6, '#ffffff');
  // Glow particles
  px(g, 9, 3, '#fbbf24');
  px(g, 22, 3, '#fbbf24');
  px(g, 7, 6, '#fde68a');
  px(g, 24, 6, '#fde68a');
  return g;
}

/** Dispatch terminal — computer terminal with cyan accents */
function dispatchTerminal() {
  const g = grid('FL');
  // Terminal body
  fill(g, 8, 8, 16, 18, '#2d2d3e');
  rect(g, 7, 7, 18, 20, '#1a1a2e');
  // Screen
  fill(g, 10, 9, 12, 8, '#0e4166');
  fill(g, 11, 10, 10, 6, 'AC');
  // Cyan scan line
  hline(g, 11, 12, 10, '#0e4166');
  // "> _" prompt
  px(g, 12, 13, '#0e4166');
  px(g, 14, 13, '#0e4166');
  // Keyboard
  fill(g, 9, 19, 14, 3, '#374151');
  for (let c = 10; c < 22; c += 2) {
    px(g, c, 20, '#4b5563');
  }
  // Accent stripe
  hline(g, 8, 23, 16, 'AC');
  // Base
  fill(g, 10, 26, 12, 2, '#374151');
  hline(g, 10, 26, 12, '#4b5563');
  return g;
}

/** Blueprint table — drafting table with grid hologram */
function blueprintTable() {
  const g = grid('FL');
  // Table surface
  fill(g, 3, 6, 26, 20, 'FN');
  rect(g, 2, 5, 28, 22, 'FS');
  hline(g, 3, 5, 26, 'FH');
  // Blueprint paper (blue grid)
  fill(g, 5, 8, 22, 16, '#1e3a5f');
  gridPattern(g, 5, 8, 22, 16, '#1e3a5f', '#2a5080', 4);
  // Drawing on blueprint
  hline(g, 8, 12, 10, '#67e8f9');
  vline(g, 18, 12, 8, '#67e8f9');
  hline(g, 12, 20, 6, '#67e8f9');
  vline(g, 8, 12, 4, '#67e8f9');
  // Pencil
  fill(g, 22, 10, 1, 6, '#fbbf24');
  px(g, 22, 16, '#374151');
  // Ruler
  fill(g, 6, 22, 16, 1, '#9ca3af');
  // Legs
  fill(g, 4, 26, 2, 4, 'FS');
  fill(g, 26, 26, 2, 4, 'FS');
  return g;
}

// ---------------------------------------------------------------------------
// Decoration tiles (8) — indices 46-53
// ---------------------------------------------------------------------------

/** Round rug */
function rugRound() {
  const g = grid('FL');
  circle(g, 16, 16, 12, 'FN');
  circle(g, 16, 16, 10, 'FH');
  circle(g, 16, 16, 8, 'FN');
  // Pattern dots
  for (let a = 0; a < 8; a++) {
    const angle = (a / 8) * Math.PI * 2;
    const rx = Math.round(16 + Math.cos(angle) * 6);
    const ry = Math.round(16 + Math.sin(angle) * 6);
    px(g, rx, ry, 'FH');
  }
  return g;
}

/** Poster A — abstract art */
function posterA() {
  const g = grid('FL');
  // Frame
  fill(g, 6, 2, 20, 26, 'FS');
  fill(g, 7, 3, 18, 24, '#e8e8e8');
  // Abstract shapes
  fill(g, 9, 5, 8, 8, '#3b82f6');
  fill(g, 13, 9, 8, 8, '#ef4444');
  fill(g, 11, 14, 8, 8, '#fbbf24');
  // Overlap areas
  fill(g, 13, 9, 4, 4, '#7c3aed');
  fill(g, 13, 14, 6, 3, '#f97316');
  return g;
}

/** Poster B — motivational/chart */
function posterB() {
  const g = grid('FL');
  // Frame
  fill(g, 6, 2, 20, 26, 'FS');
  fill(g, 7, 3, 18, 24, '#e8e8e8');
  // Bar chart
  fill(g, 10, 20, 3, 5, '#3b82f6');
  fill(g, 14, 16, 3, 9, '#10b981');
  fill(g, 18, 12, 3, 13, '#f59e0b');
  // Title lines
  hline(g, 9, 5, 14, '#374151');
  hline(g, 9, 7, 10, '#6b7280');
  return g;
}

/** Clock */
function clock() {
  const g = grid('FL');
  // Clock face
  circle(g, 16, 14, 8, 'FN');
  circle(g, 16, 14, 7, '#e8e8e8');
  circle(g, 16, 14, 6, '#f8f8f8');
  // Hour markers
  px(g, 16, 8, '#374151');  // 12
  px(g, 22, 14, '#374151'); // 3
  px(g, 16, 20, '#374151'); // 6
  px(g, 10, 14, '#374151'); // 9
  // Hands
  vline(g, 16, 10, 4, '#1a1a2e');    // hour
  hline(g, 16, 14, 4, '#374151');    // minute
  // Center dot
  px(g, 16, 14, '#ef4444');
  return g;
}

/** Ceiling light (viewed from below) */
function ceilingLight() {
  const g = grid('FL');
  // Light fixture
  circle(g, 16, 16, 6, '#fde68a');
  circle(g, 16, 16, 4, '#fef3c7');
  circle(g, 16, 16, 2, '#ffffff');
  // Glow halo
  circle(g, 16, 16, 10, null); // clear the outer ring
  for (let y = 6; y <= 26; y++) {
    for (let x = 6; x <= 26; x++) {
      const dx = x - 16;
      const dy = y - 16;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist >= 6 && dist <= 10 && g[y][x] === 'FL') {
        g[y][x] = 'FD'; // subtle glow ring on floor
      }
    }
  }
  return g;
}

/** Horizontal door (opening in a horizontal wall) */
function doorH() {
  const g = grid('WL');
  // Door opening in center
  fill(g, 8, 0, 16, 32, 'FL');
  // Door frame
  vline(g, 7, 0, 32, 'FN');
  vline(g, 24, 0, 32, 'FN');
  vline(g, 6, 0, 32, 'FS');
  vline(g, 25, 0, 32, 'FS');
  // Threshold
  fill(g, 8, 14, 16, 4, 'FH');
  return g;
}

/** Vertical door (opening in a vertical wall) */
function doorV() {
  const g = grid('WL');
  // Door opening in center
  fill(g, 0, 8, 32, 16, 'FL');
  // Door frame
  hline(g, 0, 7, 32, 'FN');
  hline(g, 0, 24, 32, 'FN');
  hline(g, 0, 6, 32, 'FS');
  hline(g, 0, 25, 32, 'FS');
  // Threshold
  fill(g, 14, 8, 4, 16, 'FH');
  return g;
}

/** Welcome mat */
function welcomeMat() {
  const g = grid('FL');
  // Mat body
  fill(g, 4, 10, 24, 12, '#5a4a3a');
  fill(g, 5, 11, 22, 10, '#6b5c4a');
  // Border decoration
  rect(g, 6, 12, 20, 8, '#8b7355');
  // "HI" text (pixel art)
  // H
  vline(g, 10, 13, 5, '#d4c5a9');
  vline(g, 13, 13, 5, '#d4c5a9');
  hline(g, 10, 15, 4, '#d4c5a9');
  // I
  vline(g, 17, 13, 5, '#d4c5a9');
  hline(g, 16, 13, 3, '#d4c5a9');
  hline(g, 16, 17, 3, '#d4c5a9');
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
];

const TILE_COLUMNS = 16;

/** Tile name → generator function mapping for new tiles */
const TILE_GENERATORS = {
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
  floor_corridor: floorCorridor,
  floor_lobby: floorLobby,
  floor_carpet_blue: () => floorCarpet('CE'),
  floor_carpet_purple: () => floorCarpet('CS'),
  floor_carpet_green: () => floorCarpet('CU'),
  floor_carpet_brown: () => floorCarpet('CR'),
  floor_carpet_indigo: () => floorCarpet('CB'),
  floor_grid: floorGrid,
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
  review_station_v2: reviewStationV2,
  dispatch_terminal: dispatchTerminal,
  blueprint_table: blueprintTable,
  rug_round: rugRound,
  poster_a: posterA,
  poster_b: posterB,
  clock: clock,
  ceiling_light: ceilingLight,
  door_h: doorH,
  door_v: doorV,
  welcome_mat: welcomeMat,
};

/**
 * Build the default environment color map for resolving palette tokens.
 * This maps 2-char tokens to hex colors from the default palette.
 */
function buildDefaultEnvColorMap() {
  return {
    FL: '#1e293b',   // floor base
    FD: '#151d2b',   // floor dark (pattern lines)
    WL: '#334155',   // wall face
    WD: '#242d3d',   // wall dark/shadow
    WH: '#5a6b80',   // wall highlight
    FN: '#4a5568',   // furniture base
    FH: '#6b7280',   // furniture highlight
    FS: '#374151',   // furniture shadow
    AC: '#67e8f9',   // accent (screens, LEDs)
    DP: '#5a4a3a',   // door wood
    CE: '#1e3a5f',   // carpet engineering
    CS: '#3b1e5f',   // carpet sales
    CU: '#1e5f3a',   // carpet support
    CR: '#5f3a1e',   // carpet research
    CB: '#2e1e5f',   // carpet blueprint
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

  const floor = presetEnv.floor || '#1e293b';
  const wall = presetEnv.wall || '#334155';
  const furnitureBase = presetEnv.furnitureBase || lighten(wall, 0.15);
  const furnitureHighlight = presetEnv.furnitureHighlight || lighten(furnitureBase, 0.2);

  return {
    FL: floor,
    FD: darken(floor, 0.25),
    WL: wall,
    WD: darken(wall, 0.3),
    WH: lighten(wall, 0.25),
    FN: furnitureBase,
    FH: furnitureHighlight,
    FS: darken(furnitureBase, 0.25),
    AC: presetEnv.reviewStation || '#67e8f9',
    DP: '#5a4a3a',
    CE: presetEnv.carpetEngineering || presetEnv.deptEngineering || '#1e3a5f',
    CS: presetEnv.carpetSales || presetEnv.deptSales || '#3b1e5f',
    CU: presetEnv.carpetSupport || presetEnv.deptSupport || '#1e5f3a',
    CR: presetEnv.carpetResearch || presetEnv.deptResearch || '#5f3a1e',
    CB: presetEnv.carpetBlueprint || '#2e1e5f',
  };
}

/**
 * Get all 54 tile grids in order.
 * Returns an object mapping tile names to grids.
 */
function getAllTiles() {
  const tiles = {};

  for (const name of TILE_ORDER) {
    if (tileTemplates[name]) {
      // Load from existing tiles.json
      tiles[name] = tileTemplates[name];
    } else if (TILE_GENERATORS[name]) {
      // Generate programmatically
      tiles[name] = TILE_GENERATORS[name]();
    } else {
      console.warn(`  warning: no tile data for "${name}"`);
      tiles[name] = grid('FL'); // fallback: plain floor
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
