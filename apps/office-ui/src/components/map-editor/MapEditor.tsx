'use client';

import { useState, useCallback, useEffect, type FC } from 'react';
import { gameEventBus } from '@/game/PhaserGame';
import { useFocusTrap } from '@/hooks/useFocusTrap';
import { useMapEditor } from '@/hooks/useMapEditor';
import { MapCanvas } from './MapCanvas';
import { TilePalette } from './TilePalette';
import { ObjectPalette } from './ObjectPalette';
import { MapToolbar } from './MapToolbar';
import { MapProperties } from './MapProperties';

interface MapEditorProps {
  open: boolean;
  onClose: () => void;
}

function InnerEditor({ onClose }: { onClose: () => void }) {
  const {
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
    setSelectedTile,
    setSelectedLayer,
    setTool,
    setMapName,
    placeTile,
    eraseTile,
    pushUndo,
    placeObject,
    removeObject,
    selectObject,
    updateObject,
    undo,
    redo,
    loadList,
    load,
    save,
    exportTmj,
    importTmj,
    newMap,
  } = useMapEditor();

  const [showGrid, setShowGrid] = useState(true);

  // Load map list on mount
  useEffect(() => {
    loadList();
  }, [loadList]);

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey) {
        if (e.key === 'z' && !e.shiftKey) {
          e.preventDefault();
          undo();
        } else if ((e.key === 'y') || (e.key === 'z' && e.shiftKey)) {
          e.preventDefault();
          redo();
        } else if (e.key === 's') {
          e.preventDefault();
          save();
        }
      } else if (e.key === 'g' && !e.ctrlKey) {
        setShowGrid((prev) => !prev);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [undo, redo, save]);

  const handleExport = useCallback(() => {
    const tmjStr = exportTmj();
    const blob = new Blob([tmjStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${mapName.replace(/\s+/g, '-').toLowerCase()}.tmj`;
    a.click();
    URL.revokeObjectURL(url);
  }, [exportTmj, mapName]);

  const handleImport = useCallback(
    (tmjStr: string) => {
      importTmj(tmjStr);
    },
    [importTmj],
  );

  const handleLoad = useCallback(
    async (id: string) => {
      await load(id);
    },
    [load],
  );

  const handleSave = useCallback(async () => {
    await save();
    await loadList();
  }, [save, loadList]);

  return (
    <div className="flex flex-col w-full h-full">
      <MapToolbar
        mapName={mapName}
        onNameChange={setMapName}
        mapList={mapList}
        currentMapId={currentMapId}
        status={status}
        showGrid={showGrid}
        canUndo={canUndo}
        canRedo={canRedo}
        onNew={() => newMap()}
        onSave={handleSave}
        onLoad={handleLoad}
        onExport={handleExport}
        onImport={handleImport}
        onUndo={undo}
        onRedo={redo}
        onGridToggle={() => setShowGrid((prev) => !prev)}
        onClose={onClose}
      />

      {error && (
        <div className="px-3 py-1 bg-red-900/50 text-red-300 text-[8px] font-mono">
          {error}
        </div>
      )}

      <div className="flex flex-1 min-h-0">
        <TilePalette
          selectedTile={selectedTile}
          selectedLayer={selectedLayer}
          onTileSelect={(id) => {
            setSelectedTile(id);
            setTool('paint');
          }}
          onLayerSelect={setSelectedLayer}
          onErase={() => {
            setSelectedTile(0);
            setTool('erase');
          }}
        />

        <MapCanvas
          map={map}
          selectedTile={selectedTile}
          selectedLayer={selectedLayer}
          tool={tool}
          showGrid={showGrid}
          selectedObject={selectedObject}
          onTilePlace={placeTile}
          onTileErase={eraseTile}
          onObjectSelect={selectObject}
          onPushUndo={pushUndo}
        />

        <ObjectPalette
          onPlaceObject={placeObject}
          onPushUndo={pushUndo}
        />

        <MapProperties
          selectedObject={selectedObject}
          onObjectUpdate={updateObject}
          onObjectRemove={removeObject}
        />
      </div>
    </div>
  );
}

export const MapEditor: FC<MapEditorProps> = ({ open, onClose }) => {
  const trapRef = useFocusTrap(open);

  // Suppress game input while editor is open
  useEffect(() => {
    if (open) {
      gameEventBus.emit('chat-focus', true);
      return () => {
        gameEventBus.emit('chat-focus', false);
      };
    }
  }, [open]);

  // ESC to close
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="absolute inset-0 z-modal animate-fade-in"
      role="dialog"
      aria-modal="true"
      aria-label="Map Editor"
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/80" onClick={onClose} />

      {/* Editor container */}
      <div
        ref={trapRef as React.RefObject<HTMLDivElement>}
        className="absolute inset-4 sm:inset-6 lg:inset-8 retro-panel pixel-border-accent animate-pop-in flex flex-col overflow-hidden"
      >
        <InnerEditor onClose={onClose} />
      </div>
    </div>
  );
};
