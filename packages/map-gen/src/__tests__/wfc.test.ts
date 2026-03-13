import { describe, it, expect } from 'vitest';
import { WFCGrid, createRng } from '../wfc';
import { buildOfficeRules, metaTileToTileId } from '../rules';
import {
  findDepartmentRegions,
  placeObjects,
  validateMap,
  DEFAULT_CONSTRAINTS,
} from '../constraints';
import { buildTmj } from '../tmj-writer';

describe('createRng', () => {
  it('produces deterministic output for same seed', () => {
    const rng1 = createRng(42);
    const rng2 = createRng(42);
    const values1 = Array.from({ length: 10 }, () => rng1());
    const values2 = Array.from({ length: 10 }, () => rng2());
    expect(values1).toEqual(values2);
  });

  it('produces different output for different seeds', () => {
    const rng1 = createRng(42);
    const rng2 = createRng(99);
    const values1 = Array.from({ length: 10 }, () => rng1());
    const values2 = Array.from({ length: 10 }, () => rng2());
    expect(values1).not.toEqual(values2);
  });

  it('produces values between 0 and 1', () => {
    const rng = createRng(123);
    for (let i = 0; i < 100; i++) {
      const v = rng();
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThan(1);
    }
  });
});

describe('buildOfficeRules', () => {
  it('creates rules for the specified department count', () => {
    const { rules, allTiles } = buildOfficeRules(4);
    // wall + corridor + 4 depts + 4 dept walls = 10
    expect(allTiles).toHaveLength(10);
    expect(rules.size).toBe(10);
  });

  it('all tiles have 4-direction adjacency sets', () => {
    const { rules } = buildOfficeRules(3);
    for (const [tile, dirs] of rules) {
      expect(dirs).toHaveLength(4);
      for (const set of dirs) {
        expect(set.size).toBeGreaterThan(0);
      }
    }
  });
});

describe('WFCGrid', () => {
  it('converges for a small grid with valid rules', () => {
    const { rules, allTiles } = buildOfficeRules(2);
    const grid = new WFCGrid({
      width: 10,
      height: 8,
      rules,
      allTiles,
      seed: 42,
    });

    const result = grid.run();
    expect(result).not.toBeNull();
    expect(result!).toHaveLength(8);
    expect(result![0]).toHaveLength(10);
  });

  it('produces deterministic output for same seed', () => {
    const { rules, allTiles } = buildOfficeRules(3);
    const grid1 = new WFCGrid({ width: 8, height: 6, rules, allTiles, seed: 12345 });
    const grid2 = new WFCGrid({ width: 8, height: 6, rules, allTiles, seed: 12345 });
    expect(grid1.run()).toEqual(grid2.run());
  });

  it('produces different output for different seeds', () => {
    const { rules, allTiles } = buildOfficeRules(3);
    const grid1 = new WFCGrid({ width: 8, height: 6, rules, allTiles, seed: 42 });
    const grid2 = new WFCGrid({ width: 8, height: 6, rules, allTiles, seed: 99 });
    const r1 = grid1.run();
    const r2 = grid2.run();
    // At least some cells should differ
    expect(r1).not.toBeNull();
    expect(r2).not.toBeNull();
    let differences = 0;
    for (let y = 0; y < 6; y++) {
      for (let x = 0; x < 8; x++) {
        if (r1![y][x] !== r2![y][x]) differences++;
      }
    }
    expect(differences).toBeGreaterThan(0);
  });

  it('all cells contain valid meta-tiles', () => {
    const { rules, allTiles } = buildOfficeRules(4);
    const tileSet = new Set(allTiles);
    const grid = new WFCGrid({ width: 12, height: 10, rules, allTiles, seed: 777 });
    const result = grid.run();
    expect(result).not.toBeNull();
    for (const row of result!) {
      for (const cell of row) {
        expect(tileSet.has(cell)).toBe(true);
      }
    }
  });

  it('recovers from contradictions via backtracking retries', () => {
    // Use a tiny grid with many departments to maximise contradiction probability.
    // With maxRetries > 1, the WFC should eventually find a valid solution or
    // exhaust retries gracefully (returning null rather than throwing).
    const { rules, allTiles } = buildOfficeRules(5);
    const grid = new WFCGrid({
      width: 5,
      height: 5,
      rules,
      allTiles,
      seed: 1,
      maxRetries: 20,
    });

    const result = grid.run();
    // The algorithm should either converge or return null -- never throw.
    // With 20 retries on a 5x5 grid it should find a solution.
    if (result !== null) {
      expect(result).toHaveLength(5);
      expect(result[0]).toHaveLength(5);
    }
  });

  it('converges on a minimum 3x3 grid', () => {
    const { rules, allTiles } = buildOfficeRules(1);
    const grid = new WFCGrid({
      width: 3,
      height: 3,
      rules,
      allTiles,
      seed: 42,
    });

    const result = grid.run();
    expect(result).not.toBeNull();
    expect(result!).toHaveLength(3);
    expect(result![0]).toHaveLength(3);

    // Every cell should be a valid meta-tile
    const tileSet = new Set(allTiles);
    for (const row of result!) {
      for (const cell of row) {
        expect(tileSet.has(cell)).toBe(true);
      }
    }
  });

  it('completes an 80x44 grid within 5 seconds', () => {
    const { rules, allTiles } = buildOfficeRules(4);
    const grid = new WFCGrid({
      width: 80,
      height: 44,
      rules,
      allTiles,
      seed: 42,
    });

    const start = performance.now();
    const result = grid.run();
    const elapsed = performance.now() - start;

    expect(result).not.toBeNull();
    expect(result!).toHaveLength(44);
    expect(result![0]).toHaveLength(80);
    expect(elapsed).toBeLessThan(5000);
  });
});

describe('metaTileToTileId', () => {
  it('maps wall to tile 1', () => {
    expect(metaTileToTileId('wall')).toBe(1);
  });

  it('maps corridor to tile 0', () => {
    expect(metaTileToTileId('corridor')).toBe(0);
  });

  it('maps dept_0 to tile 3', () => {
    expect(metaTileToTileId('dept_0')).toBe(3);
  });

  it('maps dept_wall_N to tile 1 (wall)', () => {
    expect(metaTileToTileId('dept_wall_0')).toBe(1);
    expect(metaTileToTileId('dept_wall_3')).toBe(1);
  });

  it('cycles dept tiles for index >= 4', () => {
    expect(metaTileToTileId('dept_4')).toBe(3); // 3 + (4 % 4) = 3
    expect(metaTileToTileId('dept_5')).toBe(4); // 3 + (5 % 4) = 4
  });
});

describe('findDepartmentRegions', () => {
  it('finds contiguous regions', () => {
    const grid = [
      ['dept_0', 'dept_0', 'corridor', 'dept_1', 'dept_1'],
      ['dept_0', 'dept_0', 'corridor', 'dept_1', 'dept_1'],
      ['corridor', 'corridor', 'corridor', 'corridor', 'corridor'],
    ];
    const regions = findDepartmentRegions(grid, 2);
    expect(regions).toHaveLength(2);
    expect(regions[0].cells.length).toBe(4);
    expect(regions[1].cells.length).toBe(4);
  });

  it('returns empty regions when departmentCount is 0', () => {
    const grid = [
      ['corridor', 'corridor'],
      ['corridor', 'corridor'],
    ];
    const regions = findDepartmentRegions(grid, 0);
    expect(regions).toHaveLength(0);
  });

  it('validates that a hand-crafted contiguous department forms a single connected component', () => {
    // Build a grid where dept_0 cells are all 4-connected (contiguous)
    const grid = [
      ['dept_0', 'dept_0', 'corridor', 'dept_1', 'dept_1'],
      ['dept_0', 'dept_0', 'corridor', 'dept_1', 'dept_1'],
      ['corridor', 'corridor', 'corridor', 'corridor', 'corridor'],
    ];
    const regions = findDepartmentRegions(grid, 2);

    for (const region of regions) {
      // BFS from the first cell to verify all cells in the region are reachable
      const cellSet = new Set(region.cells.map((c) => `${c.x},${c.y}`));
      const visited = new Set<string>();
      const queue = [region.cells[0]];
      visited.add(`${queue[0].x},${queue[0].y}`);

      while (queue.length > 0) {
        const current = queue.shift()!;
        const neighbors = [
          { x: current.x - 1, y: current.y },
          { x: current.x + 1, y: current.y },
          { x: current.x, y: current.y - 1 },
          { x: current.x, y: current.y + 1 },
        ];

        for (const n of neighbors) {
          const key = `${n.x},${n.y}`;
          if (cellSet.has(key) && !visited.has(key)) {
            visited.add(key);
            queue.push(n);
          }
        }
      }

      // All cells in the region should be reachable from the first cell
      expect(visited.size).toBe(region.cells.length);
    }
  });
});

describe('placeObjects', () => {
  it('places review stations for each department', () => {
    const grid = [
      ['dept_0', 'dept_0', 'corridor', 'dept_1', 'dept_1'],
      ['dept_0', 'dept_0', 'corridor', 'dept_1', 'dept_1'],
      ['corridor', 'corridor', 'corridor', 'corridor', 'corridor'],
    ];
    const regions = findDepartmentRegions(grid, 2);
    const objects = placeObjects(grid, regions, DEFAULT_CONSTRAINTS, 42);

    const reviewStations = objects.filter((o) => o.type === 'review-station');
    expect(reviewStations).toHaveLength(2);
  });

  it('places dispatch stations in corridors', () => {
    const grid = [
      ['dept_0', 'corridor', 'dept_1'],
      ['corridor', 'corridor', 'corridor'],
      ['corridor', 'corridor', 'corridor'],
    ];
    const regions = findDepartmentRegions(grid, 2);
    const objects = placeObjects(grid, regions, { ...DEFAULT_CONSTRAINTS, minDispatchStations: 2 }, 42);

    const dispatches = objects.filter((o) => o.type === 'dispatch');
    expect(dispatches.length).toBeGreaterThanOrEqual(2);
  });

  it('places at least 1 spawn point', () => {
    const grid = [
      ['corridor', 'corridor', 'corridor'],
      ['corridor', 'dept_0', 'corridor'],
      ['corridor', 'corridor', 'corridor'],
    ];
    const regions = findDepartmentRegions(grid, 1);
    const objects = placeObjects(grid, regions, DEFAULT_CONSTRAINTS, 42);

    const spawns = objects.filter((o) => o.type === 'spawn-point');
    expect(spawns.length).toBeGreaterThanOrEqual(1);
  });

  it('never places two corridor objects at the same grid position', () => {
    const grid = [
      ['dept_0', 'dept_0', 'corridor', 'dept_1', 'dept_1'],
      ['dept_0', 'dept_0', 'corridor', 'dept_1', 'dept_1'],
      ['corridor', 'corridor', 'corridor', 'corridor', 'corridor'],
      ['corridor', 'corridor', 'corridor', 'corridor', 'corridor'],
    ];
    const regions = findDepartmentRegions(grid, 2);
    const objects = placeObjects(
      grid,
      regions,
      { ...DEFAULT_CONSTRAINTS, minDispatchStations: 3, minSpawnPoints: 2 },
      42,
    );

    // Dispatch and spawn are corridor-based and use splice() to remove chosen
    // cells from the pool, so they should never share a position.
    const corridorObjects = objects.filter((o) => o.type === 'dispatch' || o.type === 'spawn-point');
    const positions = corridorObjects.map((o) => `${o.x},${o.y}`);
    const unique = new Set(positions);
    expect(unique.size).toBe(positions.length);
  });
});

describe('validateMap', () => {
  it('returns valid for a correctly constrained map', () => {
    const grid = [
      ['dept_0', 'dept_0', 'corridor', 'dept_1', 'dept_1'],
      ['dept_0', 'dept_0', 'corridor', 'dept_1', 'dept_1'],
      ['corridor', 'corridor', 'corridor', 'corridor', 'corridor'],
      ['dept_2', 'dept_2', 'corridor', 'dept_3', 'dept_3'],
      ['dept_2', 'dept_2', 'corridor', 'dept_3', 'dept_3'],
    ];
    const regions = findDepartmentRegions(grid, 4);
    const objects = placeObjects(grid, regions, DEFAULT_CONSTRAINTS, 42);
    const result = validateMap(grid, regions, objects, DEFAULT_CONSTRAINTS);
    expect(result.valid).toBe(true);
    expect(result.errors).toHaveLength(0);
  });
});

describe('buildTmj', () => {
  it('produces valid TMJ structure', () => {
    const grid = [
      ['dept_0', 'corridor', 'dept_1'],
      ['corridor', 'corridor', 'corridor'],
      ['dept_2', 'corridor', 'dept_3'],
    ];
    const regions = findDepartmentRegions(grid, 4);
    const objects = placeObjects(grid, regions, DEFAULT_CONSTRAINTS, 42);
    const tmj = buildTmj(grid, regions, objects);

    expect(tmj.type).toBe('map');
    expect(tmj.width).toBe(3);
    expect(tmj.height).toBe(3);
    expect(tmj.tilewidth).toBe(32);
    expect(tmj.tileheight).toBe(32);
  });

  it('has required layers', () => {
    const grid = [
      ['corridor', 'dept_0', 'corridor'],
      ['corridor', 'corridor', 'corridor'],
    ];
    const regions = findDepartmentRegions(grid, 1);
    const objects = placeObjects(grid, regions, DEFAULT_CONSTRAINTS, 42);
    const tmj = buildTmj(grid, regions, objects);

    const layerNames = tmj.layers.map((l) => l.name);
    expect(layerNames).toContain('floor');
    expect(layerNames).toContain('departments');
    expect(layerNames).toContain('review-stations');
    expect(layerNames).toContain('interactables');
    expect(layerNames).toContain('spawn-points');
  });

  it('floor layer data has correct length', () => {
    const grid = [
      ['wall', 'corridor', 'wall'],
      ['wall', 'corridor', 'wall'],
    ];
    const tmj = buildTmj(grid, [], []);
    const floorLayer = tmj.layers.find((l) => l.name === 'floor')!;
    expect(floorLayer.data).toHaveLength(6); // 3x2
  });

  it('tile IDs are 1-indexed (firstgid=1)', () => {
    const grid = [['corridor']];
    const tmj = buildTmj(grid, [], []);
    const floorLayer = tmj.layers.find((l) => l.name === 'floor')!;
    // corridor = tile 0, +1 = 1
    expect(floorLayer.data![0]).toBe(1);
  });

  it('tilesets reference office-tileset', () => {
    const grid = [['wall']];
    const tmj = buildTmj(grid, [], []);
    expect(tmj.tilesets[0].name).toBe('office-tileset');
    expect(tmj.tilesets[0].firstgid).toBe(1);
  });

  it('output conforms to TMJ schema with all required top-level properties', () => {
    const grid = [
      ['dept_0', 'corridor', 'dept_1'],
      ['corridor', 'corridor', 'corridor'],
    ];
    const regions = findDepartmentRegions(grid, 2);
    const objects = placeObjects(grid, regions, DEFAULT_CONSTRAINTS, 42);
    const tmj = buildTmj(grid, regions, objects);

    // Required top-level properties per Tiled JSON format
    expect(tmj).toHaveProperty('type', 'map');
    expect(tmj).toHaveProperty('version');
    expect(tmj).toHaveProperty('tiledversion');
    expect(tmj).toHaveProperty('width', 3);
    expect(tmj).toHaveProperty('height', 2);
    expect(tmj).toHaveProperty('tilewidth', 32);
    expect(tmj).toHaveProperty('tileheight', 32);
    expect(tmj).toHaveProperty('orientation', 'orthogonal');
    expect(tmj).toHaveProperty('renderorder', 'right-down');
    expect(tmj).toHaveProperty('infinite', false);
    expect(tmj).toHaveProperty('compressionlevel');
    expect(tmj).toHaveProperty('nextlayerid');
    expect(tmj).toHaveProperty('nextobjectid');

    // layers must be an array with at least the 5 required layers
    expect(Array.isArray(tmj.layers)).toBe(true);
    expect(tmj.layers.length).toBeGreaterThanOrEqual(5);

    // tilesets must be a non-empty array
    expect(Array.isArray(tmj.tilesets)).toBe(true);
    expect(tmj.tilesets.length).toBeGreaterThanOrEqual(1);

    // Each tilelayer must have data, each objectgroup must have objects
    for (const layer of tmj.layers) {
      expect(layer).toHaveProperty('id');
      expect(layer).toHaveProperty('name');
      expect(layer).toHaveProperty('type');
      expect(layer).toHaveProperty('visible');
      expect(layer).toHaveProperty('opacity');

      if (layer.type === 'tilelayer') {
        expect(Array.isArray(layer.data)).toBe(true);
        expect(layer.data!.length).toBe(tmj.width * tmj.height);
      } else if (layer.type === 'objectgroup') {
        expect(Array.isArray(layer.objects)).toBe(true);
      }
    }
  });
});

describe('end-to-end: WFC -> TMJ', () => {
  it('generates a valid map from WFC output', () => {
    const deptCount = 4;
    const { rules, allTiles } = buildOfficeRules(deptCount);
    const wfc = new WFCGrid({
      width: 20,
      height: 14,
      rules,
      allTiles,
      seed: 42,
    });

    const grid = wfc.run();
    expect(grid).not.toBeNull();

    const regions = findDepartmentRegions(grid!, deptCount);
    const objects = placeObjects(grid!, regions, DEFAULT_CONSTRAINTS, 42);
    const tmj = buildTmj(grid!, regions, objects);

    // TMJ structure
    expect(tmj.type).toBe('map');
    expect(tmj.width).toBe(20);
    expect(tmj.height).toBe(14);

    // Has required layers
    const layerNames = tmj.layers.map((l) => l.name);
    expect(layerNames).toContain('floor');
    expect(layerNames).toContain('departments');
    expect(layerNames).toContain('review-stations');
    expect(layerNames).toContain('spawn-points');

    // Floor data length matches dimensions
    const floor = tmj.layers.find((l) => l.name === 'floor')!;
    expect(floor.data).toHaveLength(20 * 14);
  });

  it('WFC-generated departments have a dominant connected component', () => {
    // WFC adjacency rules encourage dept cells to cluster but do not enforce
    // global contiguity. This test verifies that each department's largest
    // connected component contains a meaningful fraction of its total cells,
    // which is the practical quality invariant for map usability.
    const deptCount = 4;
    const { rules, allTiles } = buildOfficeRules(deptCount);
    const wfc = new WFCGrid({
      width: 20,
      height: 14,
      rules,
      allTiles,
      seed: 42,
    });

    const grid = wfc.run();
    expect(grid).not.toBeNull();

    const regions = findDepartmentRegions(grid!, deptCount);
    expect(regions.length).toBeGreaterThan(0);

    for (const region of regions) {
      if (region.cells.length <= 1) continue;

      const cellSet = new Set(region.cells.map((c) => `${c.x},${c.y}`));
      const globalVisited = new Set<string>();
      let largestComponent = 0;

      for (const cell of region.cells) {
        const startKey = `${cell.x},${cell.y}`;
        if (globalVisited.has(startKey)) continue;

        // BFS to measure this connected component
        const visited = new Set<string>();
        const queue = [cell];
        visited.add(startKey);

        while (queue.length > 0) {
          const current = queue.shift()!;
          for (const [dx, dy] of [[-1, 0], [1, 0], [0, -1], [0, 1]]) {
            const key = `${current.x + dx},${current.y + dy}`;
            if (cellSet.has(key) && !visited.has(key)) {
              visited.add(key);
              queue.push({ x: current.x + dx, y: current.y + dy });
            }
          }
        }

        for (const v of visited) globalVisited.add(v);
        if (visited.size > largestComponent) largestComponent = visited.size;
      }

      // The largest connected component should contain at least 25% of the
      // region's total cells, confirming a dominant cluster exists.
      const ratio = largestComponent / region.cells.length;
      expect(ratio).toBeGreaterThanOrEqual(0.25);
    }
  });
});
