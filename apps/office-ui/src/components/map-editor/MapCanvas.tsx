'use client';

import { useRef, useEffect, useCallback, useState, type FC, type MouseEvent, type WheelEvent, type DragEvent } from 'react';
import type { EditorMap, EditorLayer, EditorObject } from './map-converter';

interface MapCanvasProps {
  map: EditorMap;
  selectedTile: number;
  selectedLayer: string;
  tool: 'paint' | 'erase' | 'object' | 'select';
  showGrid: boolean;
  selectedObject: EditorObject | null;
  onTilePlace: (x: number, y: number) => void;
  onTileErase: (x: number, y: number) => void;
  onObjectSelect: (id: string | null) => void;
  onPushUndo: (label: string) => void;
  onImport?: (content: string) => void;
}

// Tile palette colors for visualization (indexed by tile ID)
const TILE_COLORS: Record<number, string> = {
  0: 'transparent',
  1: '#1e293b', // dark floor
  2: '#334155', // light floor
  3: '#475569', // wall
  4: '#6366f1', // department A
  5: '#22d3ee', // department B
  6: '#f59e0b', // department C
  7: '#10b981', // department D
  8: '#ef4444', // obstacle
  9: '#64748b', // furniture
  10: '#8b5cf6', // decoration
  11: '#f97316', // highlight
  12: '#0ea5e9', // water
  13: '#84cc16', // plant
  14: '#e11d48', // collision
  15: '#a855f7', // special
  16: '#0d9488', // review station
};

const OBJECT_COLORS: Record<string, string> = {
  'department': 'rgba(99,102,241,0.3)',
  'review-station': 'rgba(34,211,238,0.4)',
  'interactable': 'rgba(245,158,11,0.4)',
  'spawn-point': 'rgba(16,185,129,0.5)',
};

const OBJECT_BORDER_COLORS: Record<string, string> = {
  'department': '#6366f1',
  'review-station': '#22d3ee',
  'interactable': '#f59e0b',
  'spawn-point': '#10b981',
};

export const MapCanvas: FC<MapCanvasProps> = ({
  map,
  selectedTile,
  selectedLayer,
  tool,
  showGrid,
  selectedObject,
  onTilePlace,
  onTileErase,
  onObjectSelect,
  onPushUndo,
  onImport,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [camera, setCamera] = useState({ x: 0, y: 0, zoom: 1 });
  const [isPanning, setIsPanning] = useState(false);
  const [isPainting, setIsPainting] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);
  const panStart = useRef({ x: 0, y: 0 });
  const hasPushedUndo = useRef(false);

  // Convert screen coords to tile coords
  const screenToTile = useCallback(
    (screenX: number, screenY: number) => {
      const canvas = canvasRef.current;
      if (!canvas) return { tx: -1, ty: -1 };
      const rect = canvas.getBoundingClientRect();
      const x = (screenX - rect.left) / camera.zoom - camera.x;
      const y = (screenY - rect.top) / camera.zoom - camera.y;
      const tx = Math.floor(x / map.tileWidth);
      const ty = Math.floor(y / map.tileHeight);
      return { tx, ty };
    },
    [camera, map.tileWidth, map.tileHeight],
  );

  // Draw the map
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const w = canvas.width;
    const h = canvas.height;

    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = '#0f172a';
    ctx.fillRect(0, 0, w, h);

    ctx.save();
    ctx.scale(camera.zoom, camera.zoom);
    ctx.translate(camera.x, camera.y);

    const tw = map.tileWidth;
    const th = map.tileHeight;

    // Draw tile layers bottom to top
    for (const layer of map.layers) {
      if (!layer.visible) continue;
      for (let y = 0; y < map.height; y++) {
        for (let x = 0; x < map.width; x++) {
          const tileId = layer.data[y * map.width + x];
          if (tileId === 0) continue;
          const color = TILE_COLORS[tileId] ?? '#4b5563';
          ctx.fillStyle = color;
          ctx.fillRect(x * tw, y * th, tw, th);
        }
      }
    }

    // Draw objects
    for (const obj of map.objects) {
      const fill = OBJECT_COLORS[obj.type] ?? 'rgba(255,255,255,0.2)';
      const border = OBJECT_BORDER_COLORS[obj.type] ?? '#ffffff';
      ctx.fillStyle = fill;
      ctx.fillRect(obj.x, obj.y, obj.width, obj.height);
      ctx.strokeStyle = border;
      ctx.lineWidth = selectedObject?.id === obj.id ? 2 : 1;
      ctx.strokeRect(obj.x, obj.y, obj.width, obj.height);

      // Label
      ctx.fillStyle = '#ffffff';
      ctx.font = '8px monospace';
      const label = (obj.properties.name as string) || obj.type;
      ctx.fillText(label, obj.x + 2, obj.y + 10);
    }

    // Draw grid
    if (showGrid) {
      ctx.strokeStyle = 'rgba(148,163,184,0.15)';
      ctx.lineWidth = 0.5;
      for (let x = 0; x <= map.width; x++) {
        ctx.beginPath();
        ctx.moveTo(x * tw, 0);
        ctx.lineTo(x * tw, map.height * th);
        ctx.stroke();
      }
      for (let y = 0; y <= map.height; y++) {
        ctx.beginPath();
        ctx.moveTo(0, y * th);
        ctx.lineTo(map.width * tw, y * th);
        ctx.stroke();
      }
    }

    ctx.restore();
  }, [map, camera, showGrid, selectedObject]);

  // Resize canvas to fill container
  useEffect(() => {
    const container = containerRef.current;
    const canvas = canvasRef.current;
    if (!container || !canvas) return;
    const observer = new ResizeObserver(() => {
      canvas.width = container.clientWidth;
      canvas.height = container.clientHeight;
      draw();
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, [draw]);

  // Redraw whenever state changes
  useEffect(() => {
    draw();
  }, [draw]);

  // Mouse handlers
  const handleMouseDown = useCallback(
    (e: MouseEvent) => {
      // Middle mouse for panning
      if (e.button === 1) {
        e.preventDefault();
        setIsPanning(true);
        panStart.current = { x: e.clientX, y: e.clientY };
        return;
      }

      // Right-click to erase
      if (e.button === 2) {
        e.preventDefault();
        hasPushedUndo.current = false;
        setIsPainting(true);
        const { tx, ty } = screenToTile(e.clientX, e.clientY);
        if (tx >= 0 && tx < map.width && ty >= 0 && ty < map.height) {
          if (!hasPushedUndo.current) {
            onPushUndo('erase');
            hasPushedUndo.current = true;
          }
          onTileErase(tx, ty);
        }
        return;
      }

      // Left-click
      if (e.button === 0) {
        if (tool === 'select') {
          // Check if clicking on an object
          const { tx, ty } = screenToTile(e.clientX, e.clientY);
          const px = tx * map.tileWidth + map.tileWidth / 2;
          const py = ty * map.tileHeight + map.tileHeight / 2;
          const clicked = map.objects.find(
            (o) => px >= o.x && px <= o.x + o.width && py >= o.y && py <= o.y + o.height,
          );
          onObjectSelect(clicked?.id ?? null);
          return;
        }

        if (tool === 'paint' || tool === 'erase') {
          hasPushedUndo.current = false;
          setIsPainting(true);
          const { tx, ty } = screenToTile(e.clientX, e.clientY);
          if (tx >= 0 && tx < map.width && ty >= 0 && ty < map.height) {
            if (!hasPushedUndo.current) {
              onPushUndo(tool);
              hasPushedUndo.current = true;
            }
            if (tool === 'paint') {
              onTilePlace(tx, ty);
            } else {
              onTileErase(tx, ty);
            }
          }
        }
      }
    },
    [tool, screenToTile, map, onTilePlace, onTileErase, onObjectSelect, onPushUndo],
  );

  const handleMouseMove = useCallback(
    (e: MouseEvent) => {
      if (isPanning) {
        const dx = (e.clientX - panStart.current.x) / camera.zoom;
        const dy = (e.clientY - panStart.current.y) / camera.zoom;
        panStart.current = { x: e.clientX, y: e.clientY };
        setCamera((prev) => ({ ...prev, x: prev.x + dx, y: prev.y + dy }));
        return;
      }

      if (isPainting) {
        const { tx, ty } = screenToTile(e.clientX, e.clientY);
        if (tx >= 0 && tx < map.width && ty >= 0 && ty < map.height) {
          if (tool === 'erase' || e.buttons === 2) {
            onTileErase(tx, ty);
          } else if (tool === 'paint') {
            onTilePlace(tx, ty);
          }
        }
      }
    },
    [isPanning, isPainting, tool, screenToTile, camera.zoom, map, onTilePlace, onTileErase],
  );

  const handleMouseUp = useCallback(() => {
    setIsPanning(false);
    setIsPainting(false);
    hasPushedUndo.current = false;
  }, []);

  const handleWheel = useCallback((e: WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    setCamera((prev) => ({
      ...prev,
      zoom: Math.max(0.25, Math.min(4, prev.zoom * delta)),
    }));
  }, []);

  const handleContextMenu = useCallback((e: MouseEvent) => {
    e.preventDefault();
  }, []);

  // -- Drag-and-drop for .tmj/.json file import ----------------------------

  const handleDragOver = useCallback((e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.dataTransfer.types.includes('Files')) {
      setIsDragOver(true);
    }
  }, []);

  const handleDragLeave = useCallback((e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback(
    (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragOver(false);

      if (!onImport) return;

      const file = e.dataTransfer.files?.[0];
      if (!file) return;

      const isValid = file.name.endsWith('.tmj') || file.name.endsWith('.json');
      if (!isValid) return;

      const reader = new FileReader();
      reader.onload = () => {
        if (typeof reader.result === 'string') {
          onImport(reader.result);
        }
      };
      reader.readAsText(file);
    },
    [onImport],
  );

  return (
    <div
      ref={containerRef}
      className={`flex-1 relative overflow-hidden bg-slate-950 cursor-crosshair ${isDragOver ? 'ring-2 ring-dashed ring-indigo-400' : ''}`}
      data-testid="map-canvas-container"
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <canvas
        ref={canvasRef}
        data-testid="map-canvas"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onWheel={handleWheel}
        onContextMenu={handleContextMenu}
        className="block"
      />
      {/* Drag overlay */}
      {isDragOver && (
        <div className="absolute inset-0 flex items-center justify-center bg-indigo-900/30 pointer-events-none">
          <span className="text-retro-base text-indigo-200">Drop .tmj / .json to import</span>
        </div>
      )}
      {/* Zoom indicator */}
      <div className="absolute bottom-2 right-2 text-xs text-slate-500 font-mono">
        {Math.round(camera.zoom * 100)}%
      </div>
    </div>
  );
};
