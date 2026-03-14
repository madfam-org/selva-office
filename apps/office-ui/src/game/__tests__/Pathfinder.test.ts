import { describe, it, expect, vi } from 'vitest';
import { Pathfinder } from '../Pathfinder';

describe('Pathfinder', () => {
  it('returns direct path when no collision layer', () => {
    const pf = new Pathfinder(null, 1600, 896);
    const path = pf.findPath(100, 100, 500, 300);
    expect(path).toEqual([{ x: 500, y: 300 }]);
  });

  it('returns path with tile-center waypoints when collision layer exists', () => {
    // Mock collision layer with no blocked tiles
    const mockLayer = {
      getTileAt: vi.fn().mockReturnValue(null),
    } as unknown as Phaser.Tilemaps.TilemapLayer;

    const pf = new Pathfinder(mockLayer, 320, 320);
    const path = pf.findPath(48, 48, 144, 144);
    expect(path.length).toBeGreaterThan(0);
    // All waypoints should be tile-center aligned (multiples of 32 + 16)
    for (const wp of path) {
      expect(wp.x % 32).toBe(16);
      expect(wp.y % 32).toBe(16);
    }
  });

  it('returns direct path when destination is blocked', () => {
    const mockLayer = {
      getTileAt: vi.fn((x: number, y: number) => {
        // Block the destination tile (4, 4)
        if (x === 4 && y === 4) return { index: 1 };
        return null;
      }),
    } as unknown as Phaser.Tilemaps.TilemapLayer;

    const pf = new Pathfinder(mockLayer, 320, 320);
    const path = pf.findPath(16, 16, 144, 144);
    // Falls back to direct path since destination is blocked
    expect(path).toEqual([{ x: 144, y: 144 }]);
  });

  it('finds path around obstacles', () => {
    // Block a wall of tiles at x=3
    const mockLayer = {
      getTileAt: vi.fn((x: number, y: number) => {
        if (x === 3 && y >= 0 && y <= 3) return { index: 1 };
        return null;
      }),
    } as unknown as Phaser.Tilemaps.TilemapLayer;

    const pf = new Pathfinder(mockLayer, 320, 320);
    const path = pf.findPath(48, 48, 176, 48);
    expect(path.length).toBeGreaterThan(0);
    // Path should avoid column 3
    for (const wp of path) {
      const tileX = Math.floor((wp.x - 16) / 32);
      if (tileX === 3) {
        // If passing through column 3, y must be > 3*32+16 = 112
        expect(wp.y).toBeGreaterThan(112);
      }
    }
  });

  it('returns null-safe path when no route exists', () => {
    // Surround the start tile completely
    const mockLayer = {
      getTileAt: vi.fn((x: number, y: number) => {
        if (x === 0 && y === 0) return null; // Start tile is open
        return { index: 1 }; // Everything else blocked
      }),
    } as unknown as Phaser.Tilemaps.TilemapLayer;

    const pf = new Pathfinder(mockLayer, 320, 320);
    const path = pf.findPath(16, 16, 304, 304);
    // Should fall back to direct path when no route found
    expect(path).toEqual([{ x: 304, y: 304 }]);
  });

  it('handles same start and end position', () => {
    const pf = new Pathfinder(null, 1600, 896);
    const path = pf.findPath(100, 100, 100, 100);
    expect(path).toEqual([{ x: 100, y: 100 }]);
  });
});
