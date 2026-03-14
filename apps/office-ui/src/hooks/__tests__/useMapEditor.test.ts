import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useMapEditor } from '../useMapEditor';

// Mock apiFetch
vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/lib/api';
const mockApiFetch = vi.mocked(apiFetch);

describe('useMapEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('starts with idle status and empty map', () => {
    const { result } = renderHook(() => useMapEditor());
    expect(result.current.status).toBe('idle');
    expect(result.current.error).toBeNull();
    expect(result.current.map.width).toBe(20);
    expect(result.current.map.height).toBe(15);
    expect(result.current.map.layers).toHaveLength(5);
    expect(result.current.selectedTile).toBe(1);
    expect(result.current.selectedLayer).toBe('floor');
    expect(result.current.tool).toBe('paint');
  });

  it('placeTile updates the map layer data', () => {
    const { result } = renderHook(() => useMapEditor());

    act(() => {
      result.current.placeTile(0, 0);
    });

    const floor = result.current.map.layers.find((l) => l.name === 'floor');
    expect(floor?.data[0]).toBe(1); // selectedTile defaults to 1
  });

  it('eraseTile sets tile to 0', () => {
    const { result } = renderHook(() => useMapEditor());

    // First place a tile
    act(() => {
      result.current.placeTile(0, 0);
    });

    // Then erase it
    act(() => {
      result.current.eraseTile(0, 0);
    });

    const floor = result.current.map.layers.find((l) => l.name === 'floor');
    expect(floor?.data[0]).toBe(0);
  });

  it('placeObject adds to objects array', () => {
    const { result } = renderHook(() => useMapEditor());

    act(() => {
      result.current.placeObject({
        id: 'test_1',
        type: 'department',
        x: 100,
        y: 100,
        width: 200,
        height: 200,
        properties: { name: 'Test Dept' },
      });
    });

    expect(result.current.map.objects).toHaveLength(1);
    expect(result.current.map.objects[0].properties.name).toBe('Test Dept');
  });

  it('removeObject removes from objects array', () => {
    const { result } = renderHook(() => useMapEditor());

    act(() => {
      result.current.placeObject({
        id: 'test_1',
        type: 'department',
        x: 100,
        y: 100,
        width: 200,
        height: 200,
        properties: { name: 'Test Dept' },
      });
    });

    act(() => {
      result.current.removeObject('test_1');
    });

    expect(result.current.map.objects).toHaveLength(0);
  });

  it('undo restores previous state', () => {
    const { result } = renderHook(() => useMapEditor());

    // Push undo and place a tile
    act(() => {
      result.current.pushUndo('paint');
    });

    act(() => {
      result.current.placeTile(0, 0);
    });

    const floorAfterPaint = result.current.map.layers.find((l) => l.name === 'floor');
    expect(floorAfterPaint?.data[0]).toBe(1);

    // Undo
    act(() => {
      result.current.undo();
    });

    const floorAfterUndo = result.current.map.layers.find((l) => l.name === 'floor');
    expect(floorAfterUndo?.data[0]).toBe(0);
  });

  it('redo restores undone state', () => {
    const { result } = renderHook(() => useMapEditor());

    act(() => {
      result.current.pushUndo('paint');
    });

    act(() => {
      result.current.placeTile(0, 0);
    });

    act(() => {
      result.current.undo();
    });

    act(() => {
      result.current.redo();
    });

    const floor = result.current.map.layers.find((l) => l.name === 'floor');
    expect(floor?.data[0]).toBe(1);
  });

  it('newMap resets to empty map', () => {
    const { result } = renderHook(() => useMapEditor());

    act(() => {
      result.current.placeTile(0, 0);
    });

    act(() => {
      result.current.newMap(10, 10);
    });

    expect(result.current.map.width).toBe(10);
    expect(result.current.map.height).toBe(10);
    expect(result.current.mapName).toBe('Untitled Map');
  });

  it('loadList transitions through loading to idle', async () => {
    const maps = [
      { id: '1', name: 'Test Map', description: '', created_at: '', updated_at: '' },
    ];
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => maps,
    } as Response);

    const { result } = renderHook(() => useMapEditor());

    await act(async () => {
      await result.current.loadList();
    });

    expect(result.current.status).toBe('idle');
    expect(result.current.mapList).toEqual(maps);
  });

  it('loadList transitions to error on failure', async () => {
    mockApiFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
    } as Response);

    const { result } = renderHook(() => useMapEditor());

    await act(async () => {
      await result.current.loadList();
    });

    expect(result.current.status).toBe('error');
    expect(result.current.error).toContain('500');
  });

  it('save sends POST for new map', async () => {
    const saved = { id: '1', name: 'New Map' };
    mockApiFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => saved,
    } as Response);

    const { result } = renderHook(() => useMapEditor());

    let returned: unknown;
    await act(async () => {
      returned = await result.current.save('New Map');
    });

    expect(mockApiFetch).toHaveBeenCalledWith('/api/v1/maps', expect.objectContaining({ method: 'POST' }));
    expect(returned).toEqual(saved);
    expect(result.current.status).toBe('idle');
  });

  it('exportTmj returns valid JSON string', () => {
    const { result } = renderHook(() => useMapEditor());
    const tmjStr = result.current.exportTmj();
    const parsed = JSON.parse(tmjStr);
    expect(parsed.width).toBe(20);
    expect(parsed.height).toBe(15);
    expect(parsed.layers).toBeDefined();
  });

  it('importTmj loads TMJ data into the editor', () => {
    const { result } = renderHook(() => useMapEditor());
    const tmj = {
      width: 8,
      height: 6,
      tilewidth: 32,
      tileheight: 32,
      layers: [
        { name: 'floor', type: 'tilelayer', data: new Array(48).fill(2), visible: true },
      ],
    };

    let success: boolean = false;
    act(() => {
      success = result.current.importTmj(JSON.stringify(tmj));
    });

    expect(success).toBe(true);
    expect(result.current.map.width).toBe(8);
    expect(result.current.map.height).toBe(6);
  });
});
