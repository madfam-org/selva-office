import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { useWhiteboard } from '../../hooks/useWhiteboard';

function mockRoom() {
  return { send: vi.fn() };
}

describe('useWhiteboard', () => {
  it('starts with correct initial state', () => {
    const { result } = renderHook(() => useWhiteboard());

    expect(result.current.strokes).toEqual([]);
    expect(result.current.tool).toBe('pen');
    expect(result.current.color).toBe('#ffffff');
    expect(result.current.width).toBe(2);
    expect(result.current.colors.length).toBeGreaterThan(0);
    expect(result.current.widths.length).toBeGreaterThan(0);
  });

  it('sends stroke via room and adds optimistic local stroke', () => {
    const room = mockRoom();
    const { result } = renderHook(() => useWhiteboard({ room }));

    act(() => {
      result.current.sendStroke(10, 20, 30, 40);
    });

    expect(room.send).toHaveBeenCalledWith('draw_stroke', {
      whiteboardId: 'main',
      x: 10,
      y: 20,
      toX: 30,
      toY: 40,
      color: '#ffffff',
      width: 2,
      tool: 'pen',
    });
    expect(result.current.strokes).toHaveLength(1);
    expect(result.current.strokes[0].x).toBe(10);
  });

  it('clears the board', () => {
    const room = mockRoom();
    const { result } = renderHook(() => useWhiteboard({ room }));

    act(() => {
      result.current.sendStroke(0, 0, 10, 10);
    });
    expect(result.current.strokes).toHaveLength(1);

    act(() => {
      result.current.clearBoard();
    });

    expect(room.send).toHaveBeenCalledWith('clear_whiteboard', {
      whiteboardId: 'main',
    });
    expect(result.current.strokes).toHaveLength(0);
  });

  it('changes tool', () => {
    const { result } = renderHook(() => useWhiteboard());

    act(() => {
      result.current.setTool('eraser');
    });
    expect(result.current.tool).toBe('eraser');

    act(() => {
      result.current.setTool('pen');
    });
    expect(result.current.tool).toBe('pen');
  });

  it('changes color', () => {
    const { result } = renderHook(() => useWhiteboard());

    act(() => {
      result.current.setColor('#ff0000');
    });
    expect(result.current.color).toBe('#ff0000');
  });

  it('changes width', () => {
    const { result } = renderHook(() => useWhiteboard());

    act(() => {
      result.current.setWidth(10);
    });
    expect(result.current.width).toBe(10);
  });

  it('sends eraser stroke with tool=eraser', () => {
    const room = mockRoom();
    const { result } = renderHook(() => useWhiteboard({ room }));

    act(() => {
      result.current.setTool('eraser');
    });

    act(() => {
      result.current.sendStroke(0, 0, 10, 10);
    });

    expect(room.send).toHaveBeenCalledWith(
      'draw_stroke',
      expect.objectContaining({
        tool: 'eraser',
        color: '#000000',
        width: 10,
      }),
    );
  });

  it('syncs strokes from server', () => {
    const { result } = renderHook(() => useWhiteboard());
    const serverStrokes = [
      { x: 1, y: 2, toX: 3, toY: 4, color: '#ff0000', width: 2, tool: 'pen', senderId: 'a' },
    ];

    act(() => {
      result.current.syncStrokes(serverStrokes);
    });

    expect(result.current.strokes).toEqual(serverStrokes);
  });

  it('uses custom whiteboardId', () => {
    const room = mockRoom();
    const { result } = renderHook(() =>
      useWhiteboard({ room, whiteboardId: 'custom-board' }),
    );

    act(() => {
      result.current.sendStroke(0, 0, 10, 10);
    });

    expect(room.send).toHaveBeenCalledWith(
      'draw_stroke',
      expect.objectContaining({ whiteboardId: 'custom-board' }),
    );

    act(() => {
      result.current.clearBoard();
    });

    expect(room.send).toHaveBeenCalledWith('clear_whiteboard', {
      whiteboardId: 'custom-board',
    });
  });

  it('does not throw when room is null', () => {
    const { result } = renderHook(() => useWhiteboard({ room: null }));

    expect(() => {
      act(() => {
        result.current.sendStroke(0, 0, 10, 10);
      });
    }).not.toThrow();

    // Optimistic update still works
    expect(result.current.strokes).toHaveLength(1);
  });
});
