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
 * Matches the order in office-tileset.png:
 *   0=floor, 1=wall, 2=desk, 3=dept_engineering, 4=dept_sales,
 *   5=dept_support, 6=dept_research, 7=review_station
 */
export const TILE_ID_MAP: Record<string, number> = {
  wall: 1,
  corridor: 0,
  // dept_N maps to tile IDs 3-6 (cycling if more than 4 depts)
};

export function metaTileToTileId(metaTile: string): number {
  if (TILE_ID_MAP[metaTile] !== undefined) return TILE_ID_MAP[metaTile];
  if (metaTile.startsWith('dept_wall_')) return 1; // wall tile
  if (metaTile.startsWith('dept_')) {
    const n = parseInt(metaTile.split('_')[1], 10);
    return 3 + (n % 4); // cycle through dept tiles 3-6
  }
  return 0; // default to floor
}
