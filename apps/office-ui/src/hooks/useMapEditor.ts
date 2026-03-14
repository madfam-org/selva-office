'use client';

import { useState, useCallback, useRef } from 'react';
import { apiFetch } from '@/lib/api';
import {
  createEmptyMap,
  internalToTmj,
  tmjToInternal,
  type EditorMap,
  type EditorObject,
} from '@/components/map-editor/map-converter';

export type MapEditorTool = 'paint' | 'erase' | 'object' | 'select';
export type MapEditorStatus = 'idle' | 'loading' | 'saving' | 'error';

export interface MapSummary {
  id: string;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
}

interface UndoEntry {
  map: EditorMap;
  label: string;
}

const MAX_UNDO = 50;

export function useMapEditor() {
  const [map, setMap] = useState<EditorMap>(() => createEmptyMap());
  const [selectedTile, setSelectedTile] = useState<number>(1);
  const [selectedLayer, setSelectedLayer] = useState<string>('floor');
  const [selectedObject, setSelectedObject] = useState<EditorObject | null>(null);
  const [tool, setTool] = useState<MapEditorTool>('paint');
  const [status, setStatus] = useState<MapEditorStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  const [mapList, setMapList] = useState<MapSummary[]>([]);
  const [currentMapId, setCurrentMapId] = useState<string | null>(null);
  const [mapName, setMapName] = useState('Untitled Map');

  // Undo/redo stacks
  const undoStack = useRef<UndoEntry[]>([]);
  const redoStack = useRef<UndoEntry[]>([]);

  const pushUndo = useCallback((label: string) => {
    setMap((current) => {
      undoStack.current.push({
        map: JSON.parse(JSON.stringify(current)) as EditorMap,
        label,
      });
      if (undoStack.current.length > MAX_UNDO) {
        undoStack.current.shift();
      }
      redoStack.current = [];
      return current;
    });
  }, []);

  const undo = useCallback(() => {
    const entry = undoStack.current.pop();
    if (!entry) return;
    setMap((current) => {
      redoStack.current.push({
        map: JSON.parse(JSON.stringify(current)) as EditorMap,
        label: entry.label,
      });
      return entry.map;
    });
  }, []);

  const redo = useCallback(() => {
    const entry = redoStack.current.pop();
    if (!entry) return;
    setMap((current) => {
      undoStack.current.push({
        map: JSON.parse(JSON.stringify(current)) as EditorMap,
        label: entry.label,
      });
      return entry.map;
    });
  }, []);

  const canUndo = undoStack.current.length > 0;
  const canRedo = redoStack.current.length > 0;

  // Tile operations
  const placeTile = useCallback(
    (x: number, y: number) => {
      setMap((prev) => {
        const layer = prev.layers.find((l) => l.name === selectedLayer);
        if (!layer) return prev;
        const idx = y * prev.width + x;
        if (idx < 0 || idx >= layer.data.length) return prev;
        if (layer.data[idx] === selectedTile) return prev;
        const newData = [...layer.data];
        newData[idx] = selectedTile;
        return {
          ...prev,
          layers: prev.layers.map((l) =>
            l.name === selectedLayer ? { ...l, data: newData } : l,
          ),
        };
      });
    },
    [selectedLayer, selectedTile],
  );

  const eraseTile = useCallback(
    (x: number, y: number) => {
      setMap((prev) => {
        const layer = prev.layers.find((l) => l.name === selectedLayer);
        if (!layer) return prev;
        const idx = y * prev.width + x;
        if (idx < 0 || idx >= layer.data.length) return prev;
        if (layer.data[idx] === 0) return prev;
        const newData = [...layer.data];
        newData[idx] = 0;
        return {
          ...prev,
          layers: prev.layers.map((l) =>
            l.name === selectedLayer ? { ...l, data: newData } : l,
          ),
        };
      });
    },
    [selectedLayer],
  );

  // Object operations
  const placeObject = useCallback((obj: EditorObject) => {
    setMap((prev) => ({
      ...prev,
      objects: [...prev.objects, obj],
    }));
  }, []);

  const removeObject = useCallback((id: string) => {
    setMap((prev) => ({
      ...prev,
      objects: prev.objects.filter((o) => o.id !== id),
    }));
    setSelectedObject(null);
  }, []);

  const selectObject = useCallback(
    (id: string | null) => {
      if (!id) {
        setSelectedObject(null);
        return;
      }
      const obj = map.objects.find((o) => o.id === id) ?? null;
      setSelectedObject(obj);
    },
    [map.objects],
  );

  const updateObject = useCallback(
    (id: string, updates: Partial<EditorObject>) => {
      setMap((prev) => ({
        ...prev,
        objects: prev.objects.map((o) => (o.id === id ? { ...o, ...updates } : o)),
      }));
      setSelectedObject((prev) => {
        if (prev?.id !== id) return prev;
        return { ...prev, ...updates };
      });
    },
    [],
  );

  // API operations
  const loadList = useCallback(async () => {
    setStatus('loading');
    setError(null);
    try {
      const res = await apiFetch('/api/v1/maps');
      if (!res.ok) throw new Error(`Failed to load maps (${res.status})`);
      const data = (await res.json()) as MapSummary[];
      setMapList(data);
      setStatus('idle');
    } catch (e) {
      setError((e as Error).message);
      setStatus('error');
    }
  }, []);

  const load = useCallback(async (id: string) => {
    setStatus('loading');
    setError(null);
    try {
      const res = await apiFetch(`/api/v1/maps/${id}`);
      if (!res.ok) throw new Error(`Failed to load map (${res.status})`);
      const data = (await res.json()) as {
        id: string;
        name: string;
        tmj_content: string;
      };
      const parsed = JSON.parse(data.tmj_content) as object;
      const editorMap = tmjToInternal(parsed);
      setMap(editorMap);
      setCurrentMapId(data.id);
      setMapName(data.name);
      undoStack.current = [];
      redoStack.current = [];
      setStatus('idle');
      return data;
    } catch (e) {
      setError((e as Error).message);
      setStatus('error');
      return null;
    }
  }, []);

  const save = useCallback(
    async (name?: string) => {
      setStatus('saving');
      setError(null);
      const saveName = name ?? mapName;
      try {
        const tmj = internalToTmj(map);
        const tmjContent = JSON.stringify(tmj);
        const url = currentMapId ? `/api/v1/maps/${currentMapId}` : '/api/v1/maps';
        const method = currentMapId ? 'PUT' : 'POST';
        const res = await apiFetch(url, {
          method,
          body: JSON.stringify({
            name: saveName,
            tmj_content: tmjContent,
          }),
        });
        if (!res.ok) {
          const body = (await res.json().catch(() => ({}))) as Record<string, string>;
          throw new Error(body.detail ?? `Save failed (${res.status})`);
        }
        const data = (await res.json()) as { id: string; name: string };
        setCurrentMapId(data.id);
        setMapName(data.name);
        setStatus('idle');
        return data;
      } catch (e) {
        setError((e as Error).message);
        setStatus('error');
        return null;
      }
    },
    [map, currentMapId, mapName],
  );

  const exportTmj = useCallback(() => {
    const tmj = internalToTmj(map);
    return JSON.stringify(tmj, null, 2);
  }, [map]);

  const importTmj = useCallback((tmjString: string) => {
    try {
      const parsed = JSON.parse(tmjString) as object;
      const editorMap = tmjToInternal(parsed);
      setMap(editorMap);
      setCurrentMapId(null);
      undoStack.current = [];
      redoStack.current = [];
      return true;
    } catch {
      return false;
    }
  }, []);

  const newMap = useCallback(
    (width = 20, height = 15) => {
      pushUndo('new map');
      setMap(createEmptyMap(width, height));
      setCurrentMapId(null);
      setMapName('Untitled Map');
      setSelectedObject(null);
      undoStack.current = [];
      redoStack.current = [];
    },
    [pushUndo],
  );

  return {
    // State
    map,
    selectedTile,
    selectedLayer,
    selectedObject,
    tool,
    status,
    error,
    mapList,
    currentMapId,
    mapName,
    canUndo,
    canRedo,

    // Setters
    setSelectedTile,
    setSelectedLayer,
    setTool,
    setMapName,

    // Tile operations
    placeTile,
    eraseTile,
    pushUndo,

    // Object operations
    placeObject,
    removeObject,
    selectObject,
    updateObject,

    // Undo/Redo
    undo,
    redo,

    // API
    loadList,
    load,
    save,
    exportTmj,
    importTmj,
    newMap,
  };
}
