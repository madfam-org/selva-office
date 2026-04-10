#!/usr/bin/env node
/**
 * generate-office-map.js
 *
 * Programmatically constructs office-default.tmj with rooms, corridors,
 * furniture, and proper collision data. Outputs a 50x28 Tiled JSON map.
 *
 * FFVI / Chrono Trigger quality upgrade:
 *   - Furniture in L-shaped clusters (2-3 desks together)
 *   - floorLightPool under every ceilingLampWarm
 *   - floorShadowS/E behind/below furniture
 *   - wallMoldingTop on all wall top edges
 *   - Plants at corridor intersections and room corners
 *   - whiteboardScribbles on one wall per department
 *   - stickyNotes near desks
 *   - Central lobby with rugRoundV2 and reception desk cluster
 *   - Engineering: serverRackActive tiles (2-3)
 *   - Break area: coffeeMachineV2, plantFlowering, couch
 *   - windowDay on outer walls (2-3 per room)
 *   - awardPlaque and clockFace on walls as decoration
 *
 * Usage:
 *   node scripts/generate-office-map.js [--output path]
 */

const fs = require('node:fs');
const path = require('node:path');

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const MAP_WIDTH = 50;
const MAP_HEIGHT = 28;
const TILE_SIZE = 32;

// Tile IDs (1-indexed, tile_index + 1)
const T = {
  EMPTY: 0,
  floor: 1,
  wall: 2,
  desk: 3,
  dept_engineering: 4,
  dept_sales: 5,
  dept_support: 6,
  dept_research: 7,
  review_station: 8,
  wall_top: 9,
  wall_bottom: 10,
  wall_left: 11,
  wall_right: 12,
  wall_corner_tl: 13,
  wall_corner_tr: 14,
  wall_corner_bl: 15,
  wall_corner_br: 16,
  wall_inner_tl: 17,
  wall_inner_tr: 18,
  wall_inner_bl: 19,
  wall_inner_br: 20,
  floor_corridor: 21,
  floor_lobby: 22,
  floor_carpet_blue: 23,
  floor_carpet_purple: 24,
  floor_carpet_green: 25,
  floor_carpet_brown: 26,
  floor_carpet_indigo: 27,
  floor_grid: 28,
  desk_front: 29,
  desk_side: 30,
  chair: 31,
  monitor: 32,
  monitor_on: 33,
  bookshelf: 34,
  plant_small: 35,
  plant_large: 36,
  whiteboard: 37,
  water_cooler: 38,
  coffee_machine: 39,
  filing_cabinet: 40,
  server_rack: 41,
  printer: 42,
  couch: 43,
  review_station_v2: 44,
  dispatch_terminal: 45,
  blueprint_table: 46,
  rug_round: 47,
  poster_a: 48,
  poster_b: 49,
  clock: 50,
  ceiling_light: 51,
  door_h: 52,
  door_v: 53,
  welcome_mat: 54,
  // FFVI-quality tiles (indices 54-78 → IDs 55-79)
  desk_wood: 55,
  desk_with_coffee: 56,
  desk_with_papers: 57,
  monitor_active: 58,
  monitor_meeting: 59,
  chair_leather: 60,
  bookshelf_full: 61,
  plant_flowering: 62,
  plant_tall: 63,
  floor_shadow_s: 64,
  floor_shadow_e: 65,
  floor_light_pool: 66,
  ceiling_lamp_warm: 67,
  vent_grate: 68,
  whiteboard_scribbles: 69,
  sticky_notes: 70,
  coffee_machine_v2: 71,
  server_rack_active: 72,
  award_plaque: 73,
  clock_face: 74,
  wall_molding_top: 75,
  wall_baseboard: 76,
  window_day: 77,
  pillar: 78,
  rug_round_v2: 79,
};

// ---------------------------------------------------------------------------
// Layer helpers
// ---------------------------------------------------------------------------
function createLayer(fill = T.EMPTY) {
  return Array(MAP_WIDTH * MAP_HEIGHT).fill(fill);
}

function set(layer, col, row, tileId) {
  if (col >= 0 && col < MAP_WIDTH && row >= 0 && row < MAP_HEIGHT) {
    layer[row * MAP_WIDTH + col] = tileId;
  }
}

function get(layer, col, row) {
  if (col >= 0 && col < MAP_WIDTH && row >= 0 && row < MAP_HEIGHT) {
    return layer[row * MAP_WIDTH + col];
  }
  return T.EMPTY;
}

function fillRect(layer, x, y, w, h, tileId) {
  for (let r = y; r < y + h && r < MAP_HEIGHT; r++) {
    for (let c = x; c < x + w && c < MAP_WIDTH; c++) {
      set(layer, c, r, tileId);
    }
  }
}

// ---------------------------------------------------------------------------
// Room definitions (same 4 departments, same coordinates, FFVI-upgraded)
// ---------------------------------------------------------------------------
const ROOMS = [
  {
    name: 'Engineering',
    slug: 'dept-engineering',
    color: '#1a3d6b',
    x: 0, y: 0, w: 22, h: 12,
    carpet: T.floor_carpet_blue,
    doors: [
      { col: 10, row: 11, type: 'h' },
      { col: 11, row: 11, type: 'h' },
      { col: 21, row: 5, type: 'v' },
      { col: 21, row: 6, type: 'v' },
    ],
    furniture: [
      // === L-shaped desk cluster 1 (top-left) ===
      // 3 desks in an L: 2 facing south + 1 side desk
      { col: 2, row: 2, tile: T.desk_wood },
      { col: 3, row: 2, tile: T.desk_with_coffee },
      { col: 2, row: 1, tile: T.monitor_active },
      { col: 3, row: 1, tile: T.monitor_active },
      { col: 2, row: 3, tile: T.chair_leather },
      { col: 3, row: 3, tile: T.chair_leather },
      { col: 4, row: 2, tile: T.desk_side },       // L extension
      { col: 4, row: 1, tile: T.monitor_on },
      // Sticky notes near cluster
      { col: 5, row: 3, tile: T.sticky_notes },

      // === L-shaped desk cluster 2 (mid-left) ===
      { col: 8, row: 2, tile: T.desk_with_papers },
      { col: 9, row: 2, tile: T.desk_wood },
      { col: 8, row: 1, tile: T.monitor_active },
      { col: 9, row: 1, tile: T.monitor_on },
      { col: 8, row: 3, tile: T.chair_leather },
      { col: 9, row: 3, tile: T.chair },

      // === Desk cluster 3 (lower row) ===
      { col: 2, row: 6, tile: T.desk_wood },
      { col: 3, row: 6, tile: T.desk_with_papers },
      { col: 4, row: 6, tile: T.desk_with_coffee },
      { col: 2, row: 5, tile: T.monitor_active },
      { col: 3, row: 5, tile: T.monitor_meeting },
      { col: 4, row: 5, tile: T.monitor_active },
      { col: 2, row: 7, tile: T.chair_leather },
      { col: 3, row: 7, tile: T.chair_leather },
      { col: 4, row: 7, tile: T.chair },
      // Sticky notes near lower cluster
      { col: 5, row: 7, tile: T.sticky_notes },

      // === Server rack area (top-right corner) ===
      { col: 18, row: 1, tile: T.server_rack_active },
      { col: 19, row: 1, tile: T.server_rack_active },
      { col: 18, row: 2, tile: T.server_rack },

      // Plants at corners
      { col: 14, row: 1, tile: T.plant_tall },
      { col: 13, row: 9, tile: T.plant_flowering },

      // Printer
      { col: 14, row: 9, tile: T.printer },
    ],
    decorations: [
      // Warm lamps + light pools
      { col: 6, row: 4, tile: T.ceiling_lamp_warm },
      { col: 6, row: 5, tile: T.floor_light_pool },
      { col: 15, row: 4, tile: T.ceiling_lamp_warm },
      { col: 15, row: 5, tile: T.floor_light_pool },
      // Shadows behind furniture
      { col: 2, row: 4, tile: T.floor_shadow_s },
      { col: 3, row: 4, tile: T.floor_shadow_s },
      { col: 2, row: 8, tile: T.floor_shadow_s },
      { col: 3, row: 8, tile: T.floor_shadow_s },
      { col: 4, row: 8, tile: T.floor_shadow_s },
      // Eastern shadow near server racks
      { col: 20, row: 1, tile: T.floor_shadow_e },
      { col: 20, row: 2, tile: T.floor_shadow_e },
      // Whiteboard on wall
      { col: 12, row: 1, tile: T.whiteboard_scribbles },
      // Award plaque
      { col: 17, row: 9, tile: T.award_plaque },
      // Window on outer wall (top)
      { col: 6, row: 1, tile: T.window_day },
      { col: 16, row: 1, tile: T.window_day },
      // Vent grate
      { col: 10, row: 9, tile: T.vent_grate },
    ],
    review: { col: 18, row: 8 },
  },
  {
    name: 'Sales',
    slug: 'dept-sales',
    color: '#5a1d48',
    x: 28, y: 0, w: 22, h: 12,
    carpet: T.floor_carpet_purple,
    doors: [
      { col: 38, row: 11, type: 'h' },
      { col: 39, row: 11, type: 'h' },
      { col: 28, row: 5, type: 'v' },
      { col: 28, row: 6, type: 'v' },
    ],
    furniture: [
      // === L-shaped desk cluster 1 (left side) ===
      { col: 30, row: 2, tile: T.desk_with_coffee },
      { col: 31, row: 2, tile: T.desk_wood },
      { col: 32, row: 2, tile: T.desk_side },
      { col: 30, row: 1, tile: T.monitor_active },
      { col: 31, row: 1, tile: T.monitor_meeting },
      { col: 32, row: 1, tile: T.monitor_on },
      { col: 30, row: 3, tile: T.chair_leather },
      { col: 31, row: 3, tile: T.chair_leather },
      { col: 32, row: 3, tile: T.chair },
      // Sticky notes
      { col: 33, row: 3, tile: T.sticky_notes },

      // === Desk cluster 2 (right side) ===
      { col: 36, row: 2, tile: T.desk_wood },
      { col: 37, row: 2, tile: T.desk_with_papers },
      { col: 36, row: 1, tile: T.monitor_active },
      { col: 37, row: 1, tile: T.monitor_on },
      { col: 36, row: 3, tile: T.chair_leather },
      { col: 37, row: 3, tile: T.chair },

      // === Lower desk cluster ===
      { col: 30, row: 6, tile: T.desk_with_papers },
      { col: 31, row: 6, tile: T.desk_with_coffee },
      { col: 30, row: 5, tile: T.monitor_active },
      { col: 31, row: 5, tile: T.monitor_meeting },
      { col: 30, row: 7, tile: T.chair_leather },
      { col: 31, row: 7, tile: T.chair },
      { col: 32, row: 7, tile: T.sticky_notes },

      // Whiteboard
      { col: 46, row: 1, tile: T.whiteboard_scribbles },

      // === Break area (couch + coffee) ===
      { col: 44, row: 8, tile: T.couch },
      { col: 45, row: 8, tile: T.couch },
      { col: 47, row: 5, tile: T.coffee_machine_v2 },

      // Plants at corners
      { col: 42, row: 1, tile: T.plant_tall },
      { col: 48, row: 9, tile: T.plant_flowering },
    ],
    decorations: [
      // Warm lamps + light pools
      { col: 34, row: 4, tile: T.ceiling_lamp_warm },
      { col: 34, row: 5, tile: T.floor_light_pool },
      { col: 42, row: 4, tile: T.ceiling_lamp_warm },
      { col: 42, row: 5, tile: T.floor_light_pool },
      // Shadows
      { col: 30, row: 4, tile: T.floor_shadow_s },
      { col: 31, row: 4, tile: T.floor_shadow_s },
      { col: 30, row: 8, tile: T.floor_shadow_s },
      { col: 31, row: 8, tile: T.floor_shadow_s },
      // Windows on outer wall (top)
      { col: 34, row: 1, tile: T.window_day },
      { col: 40, row: 1, tile: T.window_day },
      { col: 48, row: 1, tile: T.window_day },
      // Clock on wall
      { col: 44, row: 1, tile: T.clock_face },
      // Award plaque
      { col: 44, row: 10, tile: T.award_plaque },
      // Vent grate
      { col: 38, row: 9, tile: T.vent_grate },
    ],
    review: { col: 44, row: 4 },
  },
  {
    name: 'Support',
    slug: 'dept-support',
    color: '#4a461d',
    x: 0, y: 16, w: 22, h: 12,
    carpet: T.floor_carpet_green,
    doors: [
      { col: 10, row: 16, type: 'h' },
      { col: 11, row: 16, type: 'h' },
      { col: 21, row: 21, type: 'v' },
      { col: 21, row: 22, type: 'v' },
    ],
    furniture: [
      // === L-shaped desk cluster 1 ===
      { col: 2, row: 18, tile: T.desk_with_coffee },
      { col: 3, row: 18, tile: T.desk_wood },
      { col: 4, row: 18, tile: T.desk_side },
      { col: 2, row: 17, tile: T.monitor_active },
      { col: 3, row: 17, tile: T.monitor_on },
      { col: 4, row: 17, tile: T.monitor_meeting },
      { col: 2, row: 19, tile: T.chair_leather },
      { col: 3, row: 19, tile: T.chair },
      { col: 4, row: 19, tile: T.chair },
      { col: 5, row: 19, tile: T.sticky_notes },

      // === Desk cluster 2 ===
      { col: 8, row: 18, tile: T.desk_wood },
      { col: 9, row: 18, tile: T.desk_with_papers },
      { col: 8, row: 17, tile: T.monitor_active },
      { col: 9, row: 17, tile: T.monitor_on },
      { col: 8, row: 19, tile: T.chair_leather },
      { col: 9, row: 19, tile: T.chair },

      // === Lower desk cluster ===
      { col: 2, row: 22, tile: T.desk_with_papers },
      { col: 3, row: 22, tile: T.desk_with_coffee },
      { col: 2, row: 21, tile: T.monitor_active },
      { col: 3, row: 21, tile: T.monitor_meeting },
      { col: 2, row: 23, tile: T.chair_leather },
      { col: 3, row: 23, tile: T.chair },
      { col: 4, row: 23, tile: T.sticky_notes },

      // Water cooler
      { col: 14, row: 17, tile: T.water_cooler },
      // Printer
      { col: 14, row: 25, tile: T.printer },
      // Plants
      { col: 19, row: 17, tile: T.plant_tall },
      { col: 13, row: 25, tile: T.plant_small },
      // Filing cabinet
      { col: 18, row: 25, tile: T.filing_cabinet },
      { col: 19, row: 25, tile: T.filing_cabinet },
      // Bookshelf
      { col: 18, row: 17, tile: T.bookshelf_full },
    ],
    decorations: [
      // Warm lamps + light pools
      { col: 6, row: 20, tile: T.ceiling_lamp_warm },
      { col: 6, row: 21, tile: T.floor_light_pool },
      { col: 15, row: 20, tile: T.ceiling_lamp_warm },
      { col: 15, row: 21, tile: T.floor_light_pool },
      // Shadows
      { col: 2, row: 20, tile: T.floor_shadow_s },
      { col: 3, row: 20, tile: T.floor_shadow_s },
      { col: 2, row: 24, tile: T.floor_shadow_s },
      { col: 3, row: 24, tile: T.floor_shadow_s },
      // Whiteboard
      { col: 12, row: 17, tile: T.whiteboard_scribbles },
      // Award and clock
      { col: 17, row: 25, tile: T.award_plaque },
      { col: 6, row: 17, tile: T.clock_face },
      // Rug
      { col: 6, row: 24, tile: T.rug_round_v2 },
      // Windows on outer wall (left)
      { col: 1, row: 19, tile: T.window_day },
      { col: 1, row: 23, tile: T.window_day },
      // Vent grate
      { col: 10, row: 25, tile: T.vent_grate },
    ],
    review: { col: 18, row: 20 },
  },
  {
    name: 'Research',
    slug: 'dept-research',
    color: '#1a4d3d',
    x: 28, y: 16, w: 22, h: 12,
    carpet: T.floor_carpet_brown,
    doors: [
      { col: 38, row: 16, type: 'h' },
      { col: 39, row: 16, type: 'h' },
      { col: 28, row: 21, type: 'v' },
      { col: 28, row: 22, type: 'v' },
    ],
    furniture: [
      // === L-shaped desk cluster 1 ===
      { col: 30, row: 18, tile: T.desk_wood },
      { col: 31, row: 18, tile: T.desk_with_papers },
      { col: 30, row: 17, tile: T.monitor_active },
      { col: 31, row: 17, tile: T.monitor_on },
      { col: 30, row: 19, tile: T.chair_leather },
      { col: 31, row: 19, tile: T.chair },
      { col: 32, row: 18, tile: T.desk_side },
      { col: 32, row: 17, tile: T.monitor_active },
      { col: 32, row: 19, tile: T.chair },
      { col: 33, row: 19, tile: T.sticky_notes },

      // === Desk cluster 2 ===
      { col: 36, row: 18, tile: T.desk_with_coffee },
      { col: 37, row: 18, tile: T.desk_wood },
      { col: 36, row: 17, tile: T.monitor_active },
      { col: 37, row: 17, tile: T.monitor_meeting },
      { col: 36, row: 19, tile: T.chair_leather },
      { col: 37, row: 19, tile: T.chair_leather },

      // Bookshelves (research library wall)
      { col: 46, row: 17, tile: T.bookshelf_full },
      { col: 47, row: 17, tile: T.bookshelf_full },
      { col: 48, row: 17, tile: T.bookshelf },

      // Whiteboard
      { col: 46, row: 21, tile: T.whiteboard_scribbles },

      // Filing cabinets
      { col: 44, row: 25, tile: T.filing_cabinet },
      { col: 45, row: 25, tile: T.filing_cabinet },

      // Plants
      { col: 42, row: 17, tile: T.plant_tall },
      { col: 48, row: 25, tile: T.plant_flowering },
    ],
    decorations: [
      // Warm lamps + light pools
      { col: 34, row: 20, tile: T.ceiling_lamp_warm },
      { col: 34, row: 21, tile: T.floor_light_pool },
      { col: 42, row: 20, tile: T.ceiling_lamp_warm },
      { col: 42, row: 21, tile: T.floor_light_pool },
      // Shadows
      { col: 30, row: 20, tile: T.floor_shadow_s },
      { col: 31, row: 20, tile: T.floor_shadow_s },
      { col: 32, row: 20, tile: T.floor_shadow_s },
      // Rug
      { col: 34, row: 24, tile: T.rug_round_v2 },
      // Windows on outer wall (right)
      { col: 48, row: 19, tile: T.window_day },
      { col: 48, row: 23, tile: T.window_day },
      // Clock
      { col: 46, row: 25, tile: T.clock_face },
      // Award
      { col: 34, row: 17, tile: T.award_plaque },
      // Vent grate
      { col: 40, row: 25, tile: T.vent_grate },
    ],
    review: { col: 44, row: 20 },
  },
];

// Blueprint zone (part of corridor, no separate room walls)
const BLUEPRINT_ZONE = {
  name: 'Blueprint Lab',
  slug: 'dept-blueprint',
  color: '#1d3458',
  x: 39, y: 12, w: 10, h: 4,
  carpet: T.floor_carpet_indigo,
  furniture: [
    { col: 42, row: 13, tile: T.blueprint_table },
    { col: 46, row: 13, tile: T.blueprint_table },
  ],
  decorations: [
    { col: 44, row: 12, tile: T.ceiling_lamp_warm },
    { col: 44, row: 13, tile: T.floor_light_pool },
  ],
};

// Central lobby furniture (FFVI reception area)
const LOBBY_FURNITURE = [
  // Reception desk cluster (placed around dispatch stations)
  { col: 22, row: 12, tile: T.desk_wood },
  { col: 23, row: 12, tile: T.desk_with_papers },
  // Rug in lobby center (walkable, behind dispatch)
  { col: 24, row: 15, tile: T.rug_round_v2 },
  // Plant at corridor intersection
  { col: 22, row: 15, tile: T.plant_flowering },
  { col: 27, row: 12, tile: T.plant_tall },
];

const LOBBY_DECORATIONS = [
  { col: 25, row: 13, tile: T.ceiling_lamp_warm },
  { col: 25, row: 14, tile: T.floor_light_pool },
];

// Corridor atmosphere
const CORRIDOR_DECORATIONS = [
  // Plants at corridor intersections
  { col: 22, row: 3, tile: T.plant_small },
  { col: 27, row: 3, tile: T.plant_small },
  { col: 22, row: 24, tile: T.plant_small },
  { col: 27, row: 24, tile: T.plant_small },
  // Warm lamps along corridors
  { col: 24, row: 5, tile: T.ceiling_lamp_warm },
  { col: 24, row: 6, tile: T.floor_light_pool },
  { col: 24, row: 22, tile: T.ceiling_lamp_warm },
  { col: 24, row: 23, tile: T.floor_light_pool },
  // Corridor pillars
  { col: 22, row: 9, tile: T.pillar },
  { col: 27, row: 9, tile: T.pillar },
  { col: 22, row: 18, tile: T.pillar },
  { col: 27, row: 18, tile: T.pillar },
];

// Break area (in corridor near Sales, between rooms)
const BREAK_AREA = {
  furniture: [
    { col: 25, row: 8, tile: T.coffee_machine_v2 },
    { col: 26, row: 8, tile: T.water_cooler },
    { col: 25, row: 9, tile: T.couch },
    { col: 26, row: 9, tile: T.couch },
    { col: 24, row: 8, tile: T.plant_flowering },
  ],
  decorations: [
    { col: 25, row: 7, tile: T.ceiling_lamp_warm },
    { col: 25, row: 10, tile: T.floor_light_pool },
  ],
};

// Corridor dispatch stations (same positions)
const DISPATCH_STATIONS = [
  { col: 24, row: 13, label: 'Dispatch Task' },
  { col: 25, row: 14, label: 'Dispatch Task' },
];

// Spawn points (same positions)
const SPAWN_POINTS = [
  { col: 24, row: 13, name: 'default-spawn' },
  { col: 25, row: 14, name: 'spawn-2' },
];

// ---------------------------------------------------------------------------
// Layer generators
// ---------------------------------------------------------------------------

/** Generate the floor layer with carpets and corridor tiles */
function generateFloorLayer() {
  const layer = createLayer(T.EMPTY);

  // Fill entire map with corridor floor as base
  fillRect(layer, 0, 0, MAP_WIDTH, MAP_HEIGHT, T.floor_corridor);

  // Room carpets (interior only, excluding walls)
  for (const room of ROOMS) {
    fillRect(layer, room.x + 1, room.y + 1, room.w - 2, room.h - 2, room.carpet);
  }

  // Lobby floor at corridor intersection
  fillRect(layer, 22, 12, 6, 4, T.floor_lobby);

  // Blueprint zone carpet
  fillRect(layer, BLUEPRINT_ZONE.x, BLUEPRINT_ZONE.y, BLUEPRINT_ZONE.w, BLUEPRINT_ZONE.h, BLUEPRINT_ZONE.carpet);

  // Welcome mats at doors
  for (const room of ROOMS) {
    for (const door of room.doors) {
      if (door.type === 'h') {
        const matRow = door.row === room.y ? door.row - 1 : door.row + 1;
        if (matRow >= 0 && matRow < MAP_HEIGHT) {
          set(layer, door.col, matRow, T.floor_corridor);
        }
      }
    }
  }

  return layer;
}

/**
 * Generate the walls layer.
 * Uses wall_molding_top for top walls of each room (FFVI quality).
 */
function generateWallsLayer() {
  const layer = createLayer(T.EMPTY);

  for (const room of ROOMS) {
    const { x, y, w, h, doors } = room;
    const x2 = x + w - 1;
    const y2 = y + h - 1;

    const doorSet = new Set(doors.map(d => `${d.col},${d.row}`));

    // Top wall (row y) — use wall_molding_top for FFVI detail
    for (let c = x + 1; c < x2; c++) {
      if (!doorSet.has(`${c},${y}`)) {
        set(layer, c, y, T.wall_molding_top);
      } else {
        set(layer, c, y, T.door_h);
      }
    }

    // Bottom wall (row y2)
    for (let c = x + 1; c < x2; c++) {
      if (!doorSet.has(`${c},${y2}`)) {
        set(layer, c, y2, T.wall_bottom);
      } else {
        set(layer, c, y2, T.door_h);
      }
    }

    // Left wall (col x)
    for (let r = y + 1; r < y2; r++) {
      if (!doorSet.has(`${x},${r}`)) {
        set(layer, x, r, T.wall_left);
      } else {
        set(layer, x, r, T.door_v);
      }
    }

    // Right wall (col x2)
    for (let r = y + 1; r < y2; r++) {
      if (!doorSet.has(`${x2},${r}`)) {
        set(layer, x2, r, T.wall_right);
      } else {
        set(layer, x2, r, T.door_v);
      }
    }

    // Corners
    set(layer, x, y, T.wall_corner_tl);
    set(layer, x2, y, T.wall_corner_tr);
    set(layer, x, y2, T.wall_corner_bl);
    set(layer, x2, y2, T.wall_corner_br);
  }

  return layer;
}

/** Generate the furniture layer (FFVI quality: clusters, variety, storytelling) */
function generateFurnitureLayer() {
  const layer = createLayer(T.EMPTY);

  // Room furniture
  for (const room of ROOMS) {
    for (const f of room.furniture) {
      set(layer, f.col, f.row, f.tile);
    }
  }

  // Blueprint zone furniture
  for (const f of BLUEPRINT_ZONE.furniture) {
    set(layer, f.col, f.row, f.tile);
  }

  // Lobby furniture
  for (const f of LOBBY_FURNITURE) {
    set(layer, f.col, f.row, f.tile);
  }

  // Break area furniture
  for (const f of BREAK_AREA.furniture) {
    set(layer, f.col, f.row, f.tile);
  }

  // Corridor dispatch terminals
  for (const d of DISPATCH_STATIONS) {
    set(layer, d.col, d.row, T.dispatch_terminal);
  }

  return layer;
}

/** Generate the decorations layer (FFVI: lamps, shadows, plaques, windows) */
function generateDecorationsLayer() {
  const layer = createLayer(T.EMPTY);

  for (const room of ROOMS) {
    for (const d of room.decorations) {
      set(layer, d.col, d.row, d.tile);
    }
  }

  for (const d of BLUEPRINT_ZONE.decorations) {
    set(layer, d.col, d.row, d.tile);
  }

  for (const d of LOBBY_DECORATIONS) {
    set(layer, d.col, d.row, d.tile);
  }

  for (const d of CORRIDOR_DECORATIONS) {
    set(layer, d.col, d.row, d.tile);
  }

  for (const d of BREAK_AREA.decorations) {
    set(layer, d.col, d.row, d.tile);
  }

  return layer;
}

/**
 * Generate the collision layer.
 * Any wall or solid furniture tile -> collision marker.
 */
function generateCollisionLayer(wallsLayer, furnitureLayer) {
  const layer = createLayer(T.EMPTY);
  const COLLISION_MARKER = T.wall;

  // Non-collidable furniture (decorative, walkable)
  const WALKABLE_FURNITURE = new Set([
    T.rug_round, T.rug_round_v2, T.ceiling_light, T.ceiling_lamp_warm,
    T.welcome_mat, T.sticky_notes, T.floor_shadow_s, T.floor_shadow_e,
    T.floor_light_pool, T.vent_grate,
  ]);

  for (let i = 0; i < MAP_WIDTH * MAP_HEIGHT; i++) {
    const wallTile = wallsLayer[i];
    const furnitureTile = furnitureLayer[i];

    // Walls block (except doors)
    if (wallTile !== T.EMPTY && wallTile !== T.door_h && wallTile !== T.door_v) {
      layer[i] = COLLISION_MARKER;
    }

    // Solid furniture blocks
    if (furnitureTile !== T.EMPTY && !WALKABLE_FURNITURE.has(furnitureTile)) {
      layer[i] = COLLISION_MARKER;
    }
  }

  return layer;
}

// ---------------------------------------------------------------------------
// Object group generators
// ---------------------------------------------------------------------------

function generateDepartmentObjects() {
  let nextId = 1;
  const objects = [];

  for (const room of ROOMS) {
    objects.push({
      id: nextId++,
      name: room.name,
      type: '',
      x: (room.x + 1) * TILE_SIZE,
      y: (room.y + 1) * TILE_SIZE,
      width: (room.w - 2) * TILE_SIZE,
      height: (room.h - 2) * TILE_SIZE,
      properties: [
        { name: 'slug', type: 'string', value: room.slug },
        { name: 'name', type: 'string', value: room.name },
        { name: 'color', type: 'string', value: room.color },
        { name: 'maxAgents', type: 'int', value: 4 },
      ],
      visible: true,
    });
  }

  // Blueprint zone (maxAgents: 0)
  objects.push({
    id: nextId++,
    name: BLUEPRINT_ZONE.name,
    type: '',
    x: BLUEPRINT_ZONE.x * TILE_SIZE,
    y: BLUEPRINT_ZONE.y * TILE_SIZE,
    width: BLUEPRINT_ZONE.w * TILE_SIZE,
    height: BLUEPRINT_ZONE.h * TILE_SIZE,
    properties: [
      { name: 'slug', type: 'string', value: BLUEPRINT_ZONE.slug },
      { name: 'name', type: 'string', value: BLUEPRINT_ZONE.name },
      { name: 'color', type: 'string', value: BLUEPRINT_ZONE.color },
      { name: 'maxAgents', type: 'int', value: 0 },
    ],
    visible: true,
  });

  return { objects, nextId };
}

function generateReviewStationObjects(startId) {
  let nextId = startId;
  const objects = [];

  for (const room of ROOMS) {
    if (room.review) {
      objects.push({
        id: nextId++,
        name: 'review-station',
        type: '',
        x: room.review.col * TILE_SIZE,
        y: room.review.row * TILE_SIZE,
        width: TILE_SIZE,
        height: TILE_SIZE,
        properties: [
          { name: 'departmentSlug', type: 'string', value: room.slug },
        ],
        visible: true,
      });
    }
  }

  return { objects, nextId };
}

function generateInteractableObjects(startId) {
  let nextId = startId;
  const objects = [];

  // Dispatch stations
  for (const d of DISPATCH_STATIONS) {
    objects.push({
      id: nextId++,
      name: 'dispatch-station',
      type: '',
      x: d.col * TILE_SIZE,
      y: d.row * TILE_SIZE,
      width: TILE_SIZE,
      height: TILE_SIZE,
      properties: [
        { name: 'interactType', type: 'string', value: 'dispatch' },
        { name: 'label', type: 'string', value: d.label },
      ],
      visible: true,
    });
  }

  // Blueprint interactable
  objects.push({
    id: nextId++,
    name: 'blueprint-station',
    type: '',
    x: 44 * TILE_SIZE,
    y: 13 * TILE_SIZE,
    width: TILE_SIZE,
    height: TILE_SIZE,
    properties: [
      { name: 'interactType', type: 'string', value: 'blueprint' },
      { name: 'label', type: 'string', value: 'Blueprint Editor' },
    ],
    visible: true,
  });

  return { objects, nextId };
}

function generateSpawnPointObjects(startId) {
  let nextId = startId;
  const objects = [];

  for (const sp of SPAWN_POINTS) {
    objects.push({
      id: nextId++,
      name: sp.name,
      type: '',
      x: sp.col * TILE_SIZE,
      y: sp.row * TILE_SIZE,
      width: TILE_SIZE,
      height: TILE_SIZE,
      visible: true,
    });
  }

  return { objects, nextId };
}

// ---------------------------------------------------------------------------
// TMJ builder
// ---------------------------------------------------------------------------

function buildTmj() {
  const floorLayer = generateFloorLayer();
  const wallsLayer = generateWallsLayer();
  const furnitureLayer = generateFurnitureLayer();
  const decorationsLayer = generateDecorationsLayer();
  const collisionLayer = generateCollisionLayer(wallsLayer, furnitureLayer);

  const { objects: deptObjects, nextId: id1 } = generateDepartmentObjects();
  const { objects: reviewObjects, nextId: id2 } = generateReviewStationObjects(id1);
  const { objects: interactableObjects, nextId: id3 } = generateInteractableObjects(id2);
  const { objects: spawnObjects, nextId: nextObjectId } = generateSpawnPointObjects(id3);

  const tileCount = 79; // 54 original + 25 FFVI tiles

  const layers = [
    {
      id: 1,
      name: 'floor',
      type: 'tilelayer',
      x: 0, y: 0,
      width: MAP_WIDTH,
      height: MAP_HEIGHT,
      data: floorLayer,
      visible: true,
      opacity: 1,
    },
    {
      id: 2,
      name: 'walls',
      type: 'tilelayer',
      x: 0, y: 0,
      width: MAP_WIDTH,
      height: MAP_HEIGHT,
      data: wallsLayer,
      visible: true,
      opacity: 1,
    },
    {
      id: 3,
      name: 'furniture',
      type: 'tilelayer',
      x: 0, y: 0,
      width: MAP_WIDTH,
      height: MAP_HEIGHT,
      data: furnitureLayer,
      visible: true,
      opacity: 1,
    },
    {
      id: 4,
      name: 'decorations',
      type: 'tilelayer',
      x: 0, y: 0,
      width: MAP_WIDTH,
      height: MAP_HEIGHT,
      data: decorationsLayer,
      visible: true,
      opacity: 1,
    },
    {
      id: 5,
      name: 'collision',
      type: 'tilelayer',
      x: 0, y: 0,
      width: MAP_WIDTH,
      height: MAP_HEIGHT,
      data: collisionLayer,
      visible: true,
      opacity: 1,
    },
    {
      id: 6,
      name: 'departments',
      type: 'objectgroup',
      x: 0, y: 0,
      objects: deptObjects,
      visible: true,
      opacity: 1,
    },
    {
      id: 7,
      name: 'review-stations',
      type: 'objectgroup',
      x: 0, y: 0,
      objects: reviewObjects,
      visible: true,
      opacity: 1,
    },
    {
      id: 8,
      name: 'interactables',
      type: 'objectgroup',
      x: 0, y: 0,
      objects: interactableObjects,
      visible: true,
      opacity: 1,
    },
    {
      id: 9,
      name: 'spawn-points',
      type: 'objectgroup',
      x: 0, y: 0,
      objects: spawnObjects,
      visible: true,
      opacity: 1,
    },
  ];

  const tileRows = Math.ceil(tileCount / 16);
  return {
    compressionlevel: -1,
    height: MAP_HEIGHT,
    width: MAP_WIDTH,
    infinite: false,
    layers,
    nextlayerid: layers.length + 1,
    nextobjectid: nextObjectId,
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
        tilecount: tileCount,
        columns: 16,
        image: '../tilesets/office-tileset.png',
        imagewidth: 512,
        imageheight: tileRows * TILE_SIZE,
      },
    ],
    type: 'map',
    version: '1.10',
    tiledversion: '1.11.0',
  };
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

function main() {
  const args = process.argv.slice(2);
  let outputPath = path.resolve(
    __dirname, '..', 'apps', 'office-ui', 'public', 'assets', 'maps', 'office-default.tmj'
  );

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--output' && args[i + 1]) {
      outputPath = path.resolve(args[++i]);
    }
  }

  const tmj = buildTmj();
  const json = JSON.stringify(tmj, null, 2);

  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, json);

  const relPath = path.relative(process.cwd(), outputPath);
  const stats = {
    layers: tmj.layers.length,
    tiles: `${MAP_WIDTH}x${MAP_HEIGHT}`,
    pixels: `${MAP_WIDTH * TILE_SIZE}x${MAP_HEIGHT * TILE_SIZE}`,
    bytes: json.length,
  };
  console.log(`Generated ${relPath}`);
  console.log(`  ${stats.layers} layers, ${stats.tiles} tiles (${stats.pixels}px), ${stats.bytes} bytes`);

  // Validate: count non-empty tiles per layer
  for (const layer of tmj.layers) {
    if (layer.type === 'tilelayer' && layer.data) {
      const nonEmpty = layer.data.filter(t => t !== 0).length;
      console.log(`  ${layer.name}: ${nonEmpty} tiles`);
    } else if (layer.type === 'objectgroup' && layer.objects) {
      console.log(`  ${layer.name}: ${layer.objects.length} objects`);
    }
  }
}

main();
