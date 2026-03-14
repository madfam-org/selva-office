'use client';

import { useCallback, useRef, type FC } from 'react';
import type { MapSummary, MapEditorStatus } from '@/hooks/useMapEditor';

interface MapToolbarProps {
  mapName: string;
  onNameChange: (name: string) => void;
  mapList: MapSummary[];
  currentMapId: string | null;
  status: MapEditorStatus;
  showGrid: boolean;
  canUndo: boolean;
  canRedo: boolean;
  onNew: () => void;
  onSave: () => void;
  onLoad: (id: string) => void;
  onExport: () => void;
  onImport: (tmj: string) => void;
  onUndo: () => void;
  onRedo: () => void;
  onGridToggle: () => void;
  onClose: () => void;
}

export const MapToolbar: FC<MapToolbarProps> = ({
  mapName,
  onNameChange,
  mapList,
  currentMapId,
  status,
  showGrid,
  canUndo,
  canRedo,
  onNew,
  onSave,
  onLoad,
  onExport,
  onImport,
  onUndo,
  onRedo,
  onGridToggle,
  onClose,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleImportClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (evt) => {
        const content = evt.target?.result;
        if (typeof content === 'string') {
          onImport(content);
        }
      };
      reader.readAsText(file);
      // Reset input so re-importing the same file works
      e.target.value = '';
    },
    [onImport],
  );

  const handleExport = useCallback(() => {
    onExport();
  }, [onExport]);

  const btnBase =
    'px-2 py-1 text-[8px] font-mono rounded transition-colors';
  const btnDefault = `${btnBase} bg-slate-700 text-slate-300 hover:bg-slate-600`;
  const btnPrimary = `${btnBase} bg-indigo-600 text-white hover:bg-indigo-500`;
  const btnDisabled = `${btnBase} bg-slate-800 text-slate-600 cursor-not-allowed`;

  return (
    <div className="flex items-center gap-2 px-3 py-2 bg-slate-900/95 border-b border-slate-700 min-h-[40px]">
      {/* Map name */}
      <input
        type="text"
        value={mapName}
        onChange={(e) => onNameChange(e.target.value)}
        className="bg-slate-800 text-slate-200 text-[10px] px-2 py-1 rounded border border-slate-600 font-mono w-40 focus:outline-none focus:border-indigo-500"
        placeholder="Map name..."
        data-testid="map-name-input"
      />

      <div className="w-px h-5 bg-slate-700" />

      {/* File operations */}
      <button onClick={onNew} className={btnDefault} title="New map">
        New
      </button>
      <button
        onClick={onSave}
        className={status === 'saving' ? btnDisabled : btnPrimary}
        disabled={status === 'saving'}
        title="Save map"
      >
        {status === 'saving' ? 'Saving...' : 'Save'}
      </button>

      {/* Load dropdown */}
      {mapList.length > 0 && (
        <select
          value={currentMapId ?? ''}
          onChange={(e) => {
            if (e.target.value) onLoad(e.target.value);
          }}
          className="bg-slate-700 text-slate-300 text-[8px] px-1 py-1 rounded border border-slate-600 font-mono max-w-[100px] focus:outline-none focus:border-indigo-500"
          title="Load saved map"
          data-testid="load-select"
        >
          <option value="">Load...</option>
          {mapList.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name}
            </option>
          ))}
        </select>
      )}

      <div className="w-px h-5 bg-slate-700" />

      {/* Import/Export */}
      <button onClick={handleExport} className={btnDefault} title="Export as TMJ file">
        Export
      </button>
      <button onClick={handleImportClick} className={btnDefault} title="Import TMJ file">
        Import
      </button>
      <input
        ref={fileInputRef}
        type="file"
        accept=".tmj,.json"
        onChange={handleFileChange}
        className="hidden"
        data-testid="import-file-input"
      />

      <div className="w-px h-5 bg-slate-700" />

      {/* Undo/Redo */}
      <button
        onClick={onUndo}
        className={canUndo ? btnDefault : btnDisabled}
        disabled={!canUndo}
        title="Undo (Ctrl+Z)"
      >
        Undo
      </button>
      <button
        onClick={onRedo}
        className={canRedo ? btnDefault : btnDisabled}
        disabled={!canRedo}
        title="Redo (Ctrl+Y)"
      >
        Redo
      </button>

      <div className="w-px h-5 bg-slate-700" />

      {/* Grid toggle */}
      <button
        onClick={onGridToggle}
        className={showGrid ? btnPrimary : btnDefault}
        title="Toggle grid"
        data-testid="grid-toggle"
      >
        Grid
      </button>

      {/* Status indicator */}
      {status === 'loading' && (
        <span className="text-[8px] text-amber-400 font-mono animate-pulse">Loading...</span>
      )}
      {status === 'error' && (
        <span className="text-[8px] text-red-400 font-mono">Error</span>
      )}

      {/* Spacer */}
      <div className="flex-1" />

      {/* Close */}
      <button onClick={onClose} className={`${btnBase} bg-red-900/50 text-red-300 hover:bg-red-800`}>
        Close
      </button>
    </div>
  );
};
