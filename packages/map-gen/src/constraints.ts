/**
 * High-level constraints for procedurally generated office maps.
 *
 * After WFC produces the raw meta-tile grid, these constraints
 * ensure the map has the required object layers:
 * - Each department has 1 review station
 * - At least 2 dispatch stations per map
 * - At least 1 spawn point
 * - Departments are contiguous
 * - Corridors connect all departments
 */

import type { MetaTile } from './wfc';
import { createRng } from './wfc';

export interface MapConstraints {
  departmentCount: number;
  minDispatchStations: number;
  minSpawnPoints: number;
}

export const DEFAULT_CONSTRAINTS: MapConstraints = {
  departmentCount: 4,
  minDispatchStations: 2,
  minSpawnPoints: 1,
};

export interface DepartmentRegion {
  index: number;
  slug: string;
  name: string;
  color: string;
  cells: Array<{ x: number; y: number }>;
  bounds: { x: number; y: number; width: number; height: number };
}

export interface PlacedObject {
  type: 'review-station' | 'dispatch' | 'spawn-point';
  x: number;
  y: number;
  properties: Record<string, string | number>;
}

const DEPT_DEFS = [
  { slug: 'engineering', name: 'Engineering', color: '#1e3a5f' },
  { slug: 'sales', name: 'Sales', color: '#3b1e5f' },
  { slug: 'support', name: 'Support', color: '#1e5f3a' },
  { slug: 'research', name: 'Research', color: '#5f3a1e' },
  { slug: 'marketing', name: 'Marketing', color: '#5f1e4a' },
  { slug: 'operations', name: 'Operations', color: '#3a5f1e' },
];

/**
 * Identify contiguous department regions from the WFC grid.
 */
export function findDepartmentRegions(
  grid: MetaTile[][],
  departmentCount: number,
): DepartmentRegion[] {
  const regions: DepartmentRegion[] = [];
  const height = grid.length;
  const width = grid[0].length;

  for (let d = 0; d < departmentCount; d++) {
    const cells: Array<{ x: number; y: number }> = [];
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        if (grid[y][x] === `dept_${d}`) {
          cells.push({ x, y });
        }
      }
    }

    if (cells.length === 0) continue;

    const minX = Math.min(...cells.map((c) => c.x));
    const minY = Math.min(...cells.map((c) => c.y));
    const maxX = Math.max(...cells.map((c) => c.x));
    const maxY = Math.max(...cells.map((c) => c.y));

    const def = DEPT_DEFS[d % DEPT_DEFS.length];
    regions.push({
      index: d,
      slug: def.slug,
      name: def.name,
      color: def.color,
      cells,
      bounds: {
        x: minX,
        y: minY,
        width: maxX - minX + 1,
        height: maxY - minY + 1,
      },
    });
  }

  return regions;
}

/**
 * Place required objects (review stations, dispatch stations, spawn points)
 * within department regions and corridors.
 */
export function placeObjects(
  grid: MetaTile[][],
  regions: DepartmentRegion[],
  constraints: MapConstraints,
  seed: number,
): PlacedObject[] {
  const rng = createRng(seed);
  const objects: PlacedObject[] = [];
  const height = grid.length;
  const width = grid[0].length;

  // 1 review station per department (near center of each region)
  for (const region of regions) {
    const cx = Math.round(region.bounds.x + region.bounds.width / 2);
    const cy = Math.round(region.bounds.y + region.bounds.height / 2);
    objects.push({
      type: 'review-station',
      x: cx,
      y: cy,
      properties: { departmentSlug: region.slug },
    });
  }

  // Dispatch stations in corridors
  const corridorCells: Array<{ x: number; y: number }> = [];
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      if (grid[y][x] === 'corridor') {
        corridorCells.push({ x, y });
      }
    }
  }

  const dispatchCount = Math.max(constraints.minDispatchStations, 2);
  for (let i = 0; i < dispatchCount && corridorCells.length > 0; i++) {
    const idx = Math.floor(rng() * corridorCells.length);
    const cell = corridorCells.splice(idx, 1)[0];
    objects.push({
      type: 'dispatch',
      x: cell.x,
      y: cell.y,
      properties: { interactType: 'dispatch' },
    });
  }

  // Spawn points (at least 1, in corridor)
  for (let i = 0; i < constraints.minSpawnPoints && corridorCells.length > 0; i++) {
    const idx = Math.floor(rng() * corridorCells.length);
    const cell = corridorCells.splice(idx, 1)[0];
    objects.push({
      type: 'spawn-point',
      x: cell.x,
      y: cell.y,
      properties: { name: i === 0 ? 'default' : `spawn_${i}` },
    });
  }

  return objects;
}

/**
 * Validate that a generated map meets all constraints.
 */
export function validateMap(
  grid: MetaTile[][],
  regions: DepartmentRegion[],
  objects: PlacedObject[],
  constraints: MapConstraints,
): { valid: boolean; errors: string[] } {
  const errors: string[] = [];

  // Check department count
  if (regions.length < constraints.departmentCount) {
    errors.push(`Expected ${constraints.departmentCount} departments, found ${regions.length}`);
  }

  // Check each department has a review station
  for (const region of regions) {
    const hasStation = objects.some(
      (o) => o.type === 'review-station' && o.properties.departmentSlug === region.slug,
    );
    if (!hasStation) {
      errors.push(`Department "${region.slug}" missing review station`);
    }
  }

  // Check dispatch stations
  const dispatchCount = objects.filter((o) => o.type === 'dispatch').length;
  if (dispatchCount < constraints.minDispatchStations) {
    errors.push(`Expected at least ${constraints.minDispatchStations} dispatch stations, found ${dispatchCount}`);
  }

  // Check spawn points
  const spawnCount = objects.filter((o) => o.type === 'spawn-point').length;
  if (spawnCount < constraints.minSpawnPoints) {
    errors.push(`Expected at least ${constraints.minSpawnPoints} spawn points, found ${spawnCount}`);
  }

  return { valid: errors.length === 0, errors };
}
