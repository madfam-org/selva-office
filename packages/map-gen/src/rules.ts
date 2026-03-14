/**
 * Adjacency rules for office meta-tiles.
 *
 * Meta-tile types:
 * - 'wall'       — boundary tiles, map edges
 * - 'corridor'   — walkable corridors connecting departments
 * - 'dept_N'     — department interior (N = 0..5)
 * - 'dept_wall_N' — department boundary walls
 *
 * Direction indices: 0=up, 1=right, 2=down, 3=left
 */

import type { AdjacencyRules, MetaTile } from './wfc';

export const META_TILES = {
  WALL: 'wall',
  CORRIDOR: 'corridor',
  dept: (n: number) => `dept_${n}`,
  deptWall: (n: number) => `dept_wall_${n}`,
} as const;

/**
 * Build adjacency rules for an office map with the given number of departments.
 */
export function buildOfficeRules(departmentCount: number): {
  rules: AdjacencyRules;
  allTiles: MetaTile[];
} {
  const allTiles: MetaTile[] = ['wall', 'corridor'];
  for (let i = 0; i < departmentCount; i++) {
    allTiles.push(`dept_${i}`, `dept_wall_${i}`);
  }

  const rules: AdjacencyRules = new Map();

  // Initialize all tiles with empty sets for each direction
  for (const tile of allTiles) {
    rules.set(tile, [new Set(), new Set(), new Set(), new Set()]);
  }

  // Wall can be adjacent to wall, corridor, and dept walls
  for (let dir = 0; dir < 4; dir++) {
    rules.get('wall')![dir].add('wall');
    rules.get('wall')![dir].add('corridor');
    for (let i = 0; i < departmentCount; i++) {
      rules.get('wall')![dir].add(`dept_wall_${i}`);
    }
  }

  // Corridor can be adjacent to wall, corridor, and dept walls
  for (let dir = 0; dir < 4; dir++) {
    rules.get('corridor')![dir].add('wall');
    rules.get('corridor')![dir].add('corridor');
    for (let i = 0; i < departmentCount; i++) {
      rules.get('corridor')![dir].add(`dept_wall_${i}`);
    }
  }

  // Department interiors adjacent to same dept interior and same dept wall
  for (let i = 0; i < departmentCount; i++) {
    const deptTile = `dept_${i}`;
    const deptWall = `dept_wall_${i}`;

    for (let dir = 0; dir < 4; dir++) {
      rules.get(deptTile)![dir].add(deptTile);
      rules.get(deptTile)![dir].add(deptWall);

      // Dept wall adjacent to dept interior, corridor, wall, and same dept wall
      rules.get(deptWall)![dir].add(deptTile);
      rules.get(deptWall)![dir].add(deptWall);
      rules.get(deptWall)![dir].add('corridor');
      rules.get(deptWall)![dir].add('wall');
    }
  }

  return { rules, allTiles };
}

/**
 * Tile ID mapping from meta-tile to Tiled tileset index.
 *
 * Tileset grid layout: 16 columns × 4 rows (512×128px)
 * Indices 0-7: original tiles (floor, wall, desk, dept_*, review_station)
 * Indices 8-19: wall variants (top, bottom, left, right, corners, inner corners)
 * Indices 20-27: floor variants (corridor, lobby, carpets, grid)
 * Indices 28-42: furniture
 * Indices 43-45: stations (review_v2, dispatch, blueprint)
 * Indices 46-53: decorations (rug, posters, clock, lights, doors, mat)
 */
export const TILE_ID_MAP: Record<string, number> = {
  wall: 1,
  corridor: 20,       // floor_corridor (was 0)
  wall_top: 8,
  wall_bottom: 9,
  wall_left: 10,
  wall_right: 11,
  wall_corner_tl: 12,
  wall_corner_tr: 13,
  wall_corner_bl: 14,
  wall_corner_br: 15,
  wall_inner_tl: 16,
  wall_inner_tr: 17,
  wall_inner_bl: 18,
  wall_inner_br: 19,
  floor_corridor: 20,
  floor_lobby: 21,
  floor_grid: 27,
  door_h: 51,
  door_v: 52,
};

/** Department carpet tile IDs by index */
const DEPT_CARPET_IDS = [22, 23, 24, 25, 26]; // blue, purple, green, brown, indigo

export function metaTileToTileId(metaTile: string): number {
  if (TILE_ID_MAP[metaTile] !== undefined) return TILE_ID_MAP[metaTile];
  if (metaTile.startsWith('dept_wall_')) return 1; // generic wall tile
  if (metaTile.startsWith('dept_')) {
    const n = parseInt(metaTile.split('_')[1], 10);
    return DEPT_CARPET_IDS[n % DEPT_CARPET_IDS.length];
  }
  return 0; // default to floor
}
