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
});
