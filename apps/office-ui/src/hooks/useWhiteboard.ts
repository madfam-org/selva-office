'use client';

import { useState, useCallback, useRef, useEffect } from 'react';

export interface WhiteboardStroke {
  x: number;
  y: number;
  toX: number;
  toY: number;
  color: string;
  width: number;
  tool: string;
  senderId: string;
}

export type WhiteboardTool = 'pen' | 'eraser';

const DEFAULT_COLORS = [
  '#ffffff',
  '#ef4444',
  '#f59e0b',
  '#22c55e',
  '#3b82f6',
  '#8b5cf6',
  '#ec4899',
  '#06b6d4',
] as const;

const DEFAULT_WIDTHS = [2, 5, 10] as const;

interface RoomLike {
  send: (type: string, data: unknown) => void;
}

interface UseWhiteboardOptions {
  whiteboardId?: string;
  room?: unknown | null;
}

export function useWhiteboard({
  whiteboardId = 'main',
  room,
}: UseWhiteboardOptions = {}) {
  const [strokes, setStrokes] = useState<WhiteboardStroke[]>([]);
  const [tool, setTool] = useState<WhiteboardTool>('pen');
  const [color, setColor] = useState<string>(DEFAULT_COLORS[0]);
  const [width, setWidth] = useState<number>(DEFAULT_WIDTHS[0]);
  const roomRef = useRef<RoomLike | null>(null);

  useEffect(() => {
    roomRef.current = room as RoomLike | null;
  }, [room]);

  const sendStroke = useCallback(
    (x: number, y: number, toX: number, toY: number) => {
      const strokeColor = tool === 'eraser' ? '#000000' : color;
      const strokeWidth = tool === 'eraser' ? 10 : width;

      roomRef.current?.send('draw_stroke', {
        whiteboardId,
        x,
        y,
        toX,
        toY,
        color: strokeColor,
        width: strokeWidth,
        tool,
      });

      // Optimistic local update
      setStrokes((prev) => [
        ...prev,
        {
          x,
          y,
          toX,
          toY,
          color: strokeColor,
          width: strokeWidth,
          tool,
          senderId: '',
        },
      ]);
    },
    [whiteboardId, tool, color, width],
  );

  const clearBoard = useCallback(() => {
    roomRef.current?.send('clear_whiteboard', { whiteboardId });
    setStrokes([]);
  }, [whiteboardId]);

  const syncStrokes = useCallback((serverStrokes: WhiteboardStroke[]) => {
    setStrokes(serverStrokes);
  }, []);

  return {
    strokes,
    tool,
    color,
    width,
    colors: DEFAULT_COLORS,
    widths: DEFAULT_WIDTHS,
    sendStroke,
    clearBoard,
    setTool,
    setColor,
    setWidth,
    syncStrokes,
  };
}
