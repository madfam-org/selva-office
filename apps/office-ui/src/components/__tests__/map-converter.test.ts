import { describe, it, expect } from 'vitest';
import { internalToTmj, tmjToInternal, createEmptyMap, type EditorMap } from '../map-editor/map-converter';

describe('map-converter', () => {
  describe('createEmptyMap', () => {
    it('creates a map with specified dimensions', () => {
      const map = createEmptyMap(10, 8);
      expect(map.width).toBe(10);
      expect(map.height).toBe(8);
      expect(map.tileWidth).toBe(32);
      expect(map.tileHeight).toBe(32);
    });

    it('creates all 5 tile layers', () => {
      const map = createEmptyMap();
      const layerNames = map.layers.map((l) => l.name);
      expect(layerNames).toContain('floor');
      expect(layerNames).toContain('walls');
      expect(layerNames).toContain('furniture');
      expect(layerNames).toContain('decorations');
      expect(layerNames).toContain('collision');
    });

    it('layer data length matches width * height', () => {
      const map = createEmptyMap(10, 8);
      for (const layer of map.layers) {
        expect(layer.data.length).toBe(80);
      }
    });

    it('all layer data initialized to 0', () => {
      const map = createEmptyMap(5, 5);
      for (const layer of map.layers) {
        expect(layer.data.every((v) => v === 0)).toBe(true);
      }
    });
  });

  describe('internalToTmj', () => {
    it('produces valid TMJ structure', () => {
      const map = createEmptyMap(10, 10);
      const tmj = internalToTmj(map) as Record<string, unknown>;

      expect(tmj.width).toBe(10);
      expect(tmj.height).toBe(10);
      expect(tmj.tilewidth).toBe(32);
      expect(tmj.tileheight).toBe(32);
      expect(tmj.orientation).toBe('orthogonal');
      expect(tmj.type).toBe('map');
    });

    it('includes all tile layers', () => {
      const map = createEmptyMap(5, 5);
      const tmj = internalToTmj(map) as Record<string, unknown>;
      const layers = tmj.layers as Array<{ name: string; type: string }>;

      const tileLayerNames = layers
        .filter((l) => l.type === 'tilelayer')
        .map((l) => l.name);

      expect(tileLayerNames).toContain('floor');
      expect(tileLayerNames).toContain('walls');
      expect(tileLayerNames).toContain('furniture');
      expect(tileLayerNames).toContain('decorations');
      expect(tileLayerNames).toContain('collision');
    });

    it('includes all object layers', () => {
      const map = createEmptyMap(5, 5);
      const tmj = internalToTmj(map) as Record<string, unknown>;
      const layers = tmj.layers as Array<{ name: string; type: string }>;

      const objectLayerNames = layers
        .filter((l) => l.type === 'objectgroup')
        .map((l) => l.name);

      expect(objectLayerNames).toContain('departments');
      expect(objectLayerNames).toContain('review-stations');
      expect(objectLayerNames).toContain('interactables');
      expect(objectLayerNames).toContain('spawn-points');
    });

    it('preserves tile data', () => {
      const map = createEmptyMap(3, 3);
      map.layers[0].data[4] = 5; // center tile of floor
      const tmj = internalToTmj(map) as Record<string, unknown>;
      const layers = tmj.layers as Array<{ name: string; data?: number[] }>;
      const floor = layers.find((l) => l.name === 'floor');
      expect(floor?.data?.[4]).toBe(5);
    });

    it('includes tileset info', () => {
      const map = createEmptyMap(5, 5);
      const tmj = internalToTmj(map) as Record<string, unknown>;
      const tilesets = tmj.tilesets as Array<{ name: string; firstgid: number }>;
      expect(tilesets).toHaveLength(1);
      expect(tilesets[0].name).toBe('office-tileset');
      expect(tilesets[0].firstgid).toBe(1);
    });
  });

  describe('tmjToInternal', () => {
    it('parses basic TMJ structure', () => {
      const tmj = {
        width: 8,
        height: 6,
        tilewidth: 32,
        tileheight: 32,
        layers: [
          { name: 'floor', type: 'tilelayer', data: new Array(48).fill(1), visible: true },
        ],
      };
      const map = tmjToInternal(tmj);
      expect(map.width).toBe(8);
      expect(map.height).toBe(6);
      expect(map.layers.find((l) => l.name === 'floor')).toBeDefined();
    });

    it('fills missing tile layers with empty data', () => {
      const tmj = {
        width: 3,
        height: 3,
        tilewidth: 32,
        tileheight: 32,
        layers: [],
      };
      const map = tmjToInternal(tmj);
      expect(map.layers).toHaveLength(5);
      for (const layer of map.layers) {
        expect(layer.data.every((v) => v === 0)).toBe(true);
      }
    });

    it('parses department objects', () => {
      const tmj = {
        width: 10,
        height: 10,
        tilewidth: 32,
        tileheight: 32,
        layers: [
          {
            name: 'departments',
            type: 'objectgroup',
            objects: [
              {
                id: 1,
                name: 'Engineering',
                type: '',
                x: 64,
                y: 32,
                width: 256,
                height: 192,
                properties: [
                  { name: 'slug', type: 'string', value: 'engineering' },
                ],
                visible: true,
              },
            ],
            visible: true,
            opacity: 1,
          },
        ],
      };
      const map = tmjToInternal(tmj);
      expect(map.objects).toHaveLength(1);
      expect(map.objects[0].type).toBe('department');
      expect(map.objects[0].properties.slug).toBe('engineering');
    });
  });

  describe('roundtrip', () => {
    it('preserves map data through internal -> TMJ -> internal', () => {
      const original: EditorMap = {
        width: 8,
        height: 6,
        tileWidth: 32,
        tileHeight: 32,
        layers: [
          { name: 'floor', data: Array.from({ length: 48 }, (_, i) => i % 3), visible: true },
          { name: 'walls', data: new Array(48).fill(0), visible: true },
          { name: 'furniture', data: new Array(48).fill(0), visible: true },
          { name: 'decorations', data: new Array(48).fill(0), visible: true },
          { name: 'collision', data: new Array(48).fill(0), visible: true },
        ],
        objects: [
          {
            id: 'obj_1',
            type: 'department',
            x: 64,
            y: 32,
            width: 256,
            height: 192,
            properties: { name: 'Engineering', slug: 'engineering', color: '#6366f1' },
          },
          {
            id: 'obj_2',
            type: 'spawn-point',
            x: 96,
            y: 96,
            width: 32,
            height: 32,
            properties: { name: 'player-spawn' },
          },
        ],
      };

      const tmj = internalToTmj(original);
      const roundtripped = tmjToInternal(tmj);

      expect(roundtripped.width).toBe(original.width);
      expect(roundtripped.height).toBe(original.height);

      // Floor data preserved
      const originalFloor = original.layers.find((l) => l.name === 'floor');
      const roundtrippedFloor = roundtripped.layers.find((l) => l.name === 'floor');
      expect(roundtrippedFloor?.data).toEqual(originalFloor?.data);

      // Objects preserved (IDs will differ but types and properties match)
      expect(roundtripped.objects).toHaveLength(2);
      const dept = roundtripped.objects.find((o) => o.type === 'department');
      expect(dept?.properties.slug).toBe('engineering');
      const spawn = roundtripped.objects.find((o) => o.type === 'spawn-point');
      expect(spawn?.properties.name).toBe('player-spawn');
    });

    it('preserves layer names through roundtrip', () => {
      const map = createEmptyMap(5, 5);
      const tmj = internalToTmj(map);
      const roundtripped = tmjToInternal(tmj);

      const originalNames = map.layers.map((l) => l.name).sort();
      const roundtrippedNames = roundtripped.layers.map((l) => l.name).sort();
      expect(roundtrippedNames).toEqual(originalNames);
    });
  });
});
