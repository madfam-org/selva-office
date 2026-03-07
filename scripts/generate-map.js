#!/usr/bin/env node
/**
 * generate-map.js
 *
 * CLI for WFC-based procedural office map generation.
 * Outputs a valid .tmj file compatible with TiledMapLoader.ts.
 *
 * Usage:
 *   node scripts/generate-map.js [--seed N] [--departments N] [--width N] [--height N] [--output path]
 */

// Since map-gen is a TypeScript package, we use the source directly via tsx or
// just re-implement the pipeline in JS by importing the built output.
// For simplicity, we inline the same logic here using the WFC algorithm.

const fs = require('node:fs');
const path = require('node:path');

// ---------------------------------------------------------------------------
// Seeded PRNG (mulberry32)
// ---------------------------------------------------------------------------
function createRng(seed) {
  let s = seed | 0;
  return () => {
    s = (s + 0x6d2b79f5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// ---------------------------------------------------------------------------
// Simplified procedural map generation
// Uses a zone-placement approach for reliable results:
// 1. Fill map with walls/corridors
// 2. Place department zones in quadrants
// 3. Connect them with corridors
// 4. Place required objects
// ---------------------------------------------------------------------------

const DEPT_DEFS = [
  { slug: 'engineering', name: 'Engineering', color: '#1e3a5f' },
  { slug: 'sales', name: 'Sales', color: '#3b1e5f' },
  { slug: 'support', name: 'Support', color: '#1e5f3a' },
  { slug: 'research', name: 'Research', color: '#5f3a1e' },
  { slug: 'marketing', name: 'Marketing', color: '#5f1e4a' },
  { slug: 'operations', name: 'Operations', color: '#3a5f1e' },
];

// Tile IDs matching office-tileset.png order
const TILE_IDS = {
  floor: 0,
  wall: 1,
  desk: 2,
  dept_engineering: 3,
  dept_sales: 4,
  dept_support: 5,
  dept_research: 6,
  review_station: 7,
};

function parseArgs() {
  const args = process.argv.slice(2);
  const opts = {
    seed: 42,
    departments: 4,
    width: 40,
    height: 22,
    output: path.resolve(__dirname, '..', 'apps', 'office-ui', 'public', 'assets', 'maps', 'office-generated.tmj'),
  };

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--seed' && args[i + 1]) opts.seed = parseInt(args[++i], 10);
    if (args[i] === '--departments' && args[i + 1]) opts.departments = Math.min(6, Math.max(2, parseInt(args[++i], 10)));
    if (args[i] === '--width' && args[i + 1]) opts.width = parseInt(args[++i], 10);
    if (args[i] === '--height' && args[i + 1]) opts.height = parseInt(args[++i], 10);
    if (args[i] === '--output' && args[i + 1]) opts.output = path.resolve(args[++i]);
  }

  return opts;
}

function generateMap(opts) {
  const { seed, departments, width, height } = opts;
  const rng = createRng(seed);

  // Initialize grid: walls on borders, floor elsewhere
  const grid = [];
  for (let y = 0; y < height; y++) {
    const row = [];
    for (let x = 0; x < width; x++) {
      if (x === 0 || x === width - 1 || y === 0 || y === height - 1) {
        row.push('wall');
      } else {
        row.push('floor');
      }
    }
    grid.push(row);
  }

  // Calculate department zone placement
  const innerW = width - 2;
  const innerH = height - 2;
  const cols = Math.ceil(Math.sqrt(departments));
  const rows = Math.ceil(departments / cols);
  const zoneW = Math.floor(innerW / cols);
  const zoneH = Math.floor(innerH / rows);
  const padding = 1; // gap between zones for corridors

  const regions = [];

  for (let d = 0; d < departments; d++) {
    const col = d % cols;
    const row = Math.floor(d / cols);
    const zx = 1 + col * zoneW + padding;
    const zy = 1 + row * zoneH + padding;
    const zw = zoneW - padding * 2;
    const zh = zoneH - padding * 2;

    const def = DEPT_DEFS[d % DEPT_DEFS.length];
    const deptTileId = 3 + (d % 4); // cycle through dept tile IDs

    // Fill department area
    for (let dy = 0; dy < zh; dy++) {
      for (let dx = 0; dx < zw; dx++) {
        const px = zx + dx;
        const py = zy + dy;
        if (px > 0 && px < width - 1 && py > 0 && py < height - 1) {
          grid[py][px] = `dept_${d}`;
        }
      }
    }

    regions.push({
      index: d,
      slug: def.slug,
      name: def.name,
      color: def.color,
      x: zx,
      y: zy,
      width: zw,
      height: zh,
      tileId: deptTileId,
    });
  }

  // Corridors: horizontal and vertical through the center
  const midY = Math.floor(height / 2);
  const midX = Math.floor(width / 2);

  // Horizontal corridor
  for (let x = 1; x < width - 1; x++) {
    grid[midY][x] = 'corridor';
    if (midY + 1 < height - 1) grid[midY + 1][x] = 'corridor';
  }

  // Vertical corridor
  for (let y = 1; y < height - 1; y++) {
    grid[y][midX] = 'corridor';
    if (midX + 1 < width - 1) grid[y][midX + 1] = 'corridor';
  }

  // Additional corridors between dept zones (vertical)
  for (let c = 1; c < cols; c++) {
    const cx = 1 + c * zoneW;
    for (let y = 1; y < height - 1; y++) {
      grid[y][cx] = 'corridor';
    }
  }

  // Additional corridors between dept zones (horizontal)
  for (let r = 1; r < rows; r++) {
    const cy = 1 + r * zoneH;
    for (let x = 1; x < width - 1; x++) {
      if (cy < height - 1) grid[cy][x] = 'corridor';
    }
  }

  return { grid, regions, rng };
}

function buildTmj(opts, grid, regions, rng) {
  const { width, height } = opts;
  const TILE_SIZE = 32;

  // Floor data (1-indexed)
  const floorData = [];
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const cell = grid[y][x];
      let tileId;
      if (cell === 'wall') tileId = 1;
      else if (cell === 'corridor' || cell === 'floor') tileId = 0;
      else if (cell.startsWith('dept_')) {
        const d = parseInt(cell.split('_')[1], 10);
        tileId = 3 + (d % 4);
      } else {
        tileId = 0;
      }
      floorData.push(tileId + 1); // 1-indexed
    }
  }

  let nextObjId = 1;

  // Department objects
  const deptObjects = regions.map((r) => ({
    id: nextObjId++,
    name: r.name,
    type: '',
    x: r.x * TILE_SIZE,
    y: r.y * TILE_SIZE,
    width: r.width * TILE_SIZE,
    height: r.height * TILE_SIZE,
    properties: [
      { name: 'slug', type: 'string', value: r.slug },
      { name: 'name', type: 'string', value: r.name },
      { name: 'color', type: 'string', value: r.color },
      { name: 'maxAgents', type: 'int', value: 4 },
    ],
    visible: true,
  }));

  // Review stations (1 per dept, near center)
  const reviewObjects = regions.map((r) => ({
    id: nextObjId++,
    name: 'review-station',
    type: '',
    x: Math.round(r.x + r.width / 2) * TILE_SIZE,
    y: Math.round(r.y + r.height / 2) * TILE_SIZE,
    width: TILE_SIZE,
    height: TILE_SIZE,
    properties: [
      { name: 'departmentSlug', type: 'string', value: r.slug },
    ],
    visible: true,
  }));

  // Dispatch stations (in corridors)
  const corridorCells = [];
  for (let y = 1; y < height - 1; y++) {
    for (let x = 1; x < width - 1; x++) {
      if (grid[y][x] === 'corridor') corridorCells.push({ x, y });
    }
  }

  const dispatchObjects = [];
  for (let i = 0; i < 2 && corridorCells.length > 0; i++) {
    const idx = Math.floor(rng() * corridorCells.length);
    const cell = corridorCells.splice(idx, 1)[0];
    dispatchObjects.push({
      id: nextObjId++,
      name: 'dispatch-station',
      type: '',
      x: cell.x * TILE_SIZE,
      y: cell.y * TILE_SIZE,
      width: TILE_SIZE,
      height: TILE_SIZE,
      properties: [
        { name: 'interactType', type: 'string', value: 'dispatch' },
        { name: 'label', type: 'string', value: 'Dispatch Task' },
      ],
      visible: true,
    });
  }

  // Spawn point
  const spawnObjects = [];
  if (corridorCells.length > 0) {
    const idx = Math.floor(rng() * corridorCells.length);
    const cell = corridorCells[idx];
    spawnObjects.push({
      id: nextObjId++,
      name: 'default',
      type: '',
      x: cell.x * TILE_SIZE,
      y: cell.y * TILE_SIZE,
      width: TILE_SIZE,
      height: TILE_SIZE,
      visible: true,
    });
  }

  return {
    compressionlevel: -1,
    height,
    width,
    infinite: false,
    layers: [
      { id: 1, name: 'floor', type: 'tilelayer', x: 0, y: 0, width, height, data: floorData, visible: true, opacity: 1 },
      { id: 2, name: 'departments', type: 'objectgroup', x: 0, y: 0, objects: deptObjects, visible: true, opacity: 1 },
      { id: 3, name: 'review-stations', type: 'objectgroup', x: 0, y: 0, objects: reviewObjects, visible: true, opacity: 1 },
      { id: 4, name: 'interactables', type: 'objectgroup', x: 0, y: 0, objects: dispatchObjects, visible: true, opacity: 1 },
      { id: 5, name: 'spawn-points', type: 'objectgroup', x: 0, y: 0, objects: spawnObjects, visible: true, opacity: 1 },
    ],
    nextlayerid: 6,
    nextobjectid: nextObjId,
    orientation: 'orthogonal',
    renderorder: 'right-down',
    tileheight: TILE_SIZE,
    tilewidth: TILE_SIZE,
    tilesets: [
      {
        firstgid: 1,
        name: 'office-tileset',
        tilewidth: TILE_SIZE,
        tileheight: TILE_SIZE,
        tilecount: 8,
        columns: 8,
        image: '../tilesets/office-tileset.png',
        imagewidth: 256,
        imageheight: 32,
      },
    ],
    type: 'map',
    version: '1.10',
    tiledversion: '1.11.0',
  };
}

function main() {
  const opts = parseArgs();

  console.log(`Generating map: ${opts.width}x${opts.height}, ${opts.departments} departments, seed=${opts.seed}`);

  const { grid, regions, rng } = generateMap(opts);
  const tmj = buildTmj(opts, grid, regions, rng);

  // Validate
  const layerNames = tmj.layers.map((l) => l.name);
  const requiredLayers = ['floor', 'departments', 'review-stations', 'interactables', 'spawn-points'];
  for (const required of requiredLayers) {
    if (!layerNames.includes(required)) {
      console.error(`ERROR: Missing required layer "${required}"`);
      process.exit(1);
    }
  }

  const floorLayer = tmj.layers.find((l) => l.name === 'floor');
  if (floorLayer.data.length !== opts.width * opts.height) {
    console.error(`ERROR: Floor data length ${floorLayer.data.length} != ${opts.width * opts.height}`);
    process.exit(1);
  }

  fs.mkdirSync(path.dirname(opts.output), { recursive: true });
  fs.writeFileSync(opts.output, JSON.stringify(tmj, null, 2));

  const deptLayer = tmj.layers.find((l) => l.name === 'departments');
  const reviewLayer = tmj.layers.find((l) => l.name === 'review-stations');
  const spawnLayer = tmj.layers.find((l) => l.name === 'spawn-points');

  console.log(`  Departments: ${deptLayer.objects.length}`);
  console.log(`  Review stations: ${reviewLayer.objects.length}`);
  console.log(`  Spawn points: ${spawnLayer.objects.length}`);
  console.log(`  Wrote ${path.relative(process.cwd(), opts.output)}`);
}

main();
