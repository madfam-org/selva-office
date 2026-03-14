'use client';

import { type FC } from 'react';

const LAYERS = ['floor', 'walls', 'furniture', 'decorations', 'collision'] as const;

const TILE_DEFS: { id: number; name: string; color: string; category: string }[] = [
  { id: 1, name: 'Dark Floor', color: '#1e293b', category: 'floor' },
  { id: 2, name: 'Light Floor', color: '#334155', category: 'floor' },
  { id: 3, name: 'Wall', color: '#475569', category: 'walls' },
  { id: 4, name: 'Dept A', color: '#6366f1', category: 'floor' },
  { id: 5, name: 'Dept B', color: '#22d3ee', category: 'floor' },
  { id: 6, name: 'Dept C', color: '#f59e0b', category: 'floor' },
  { id: 7, name: 'Dept D', color: '#10b981', category: 'floor' },
  { id: 8, name: 'Obstacle', color: '#ef4444', category: 'walls' },
  { id: 9, name: 'Furniture', color: '#64748b', category: 'furniture' },
  { id: 10, name: 'Decor', color: '#8b5cf6', category: 'decorations' },
  { id: 11, name: 'Highlight', color: '#f97316', category: 'decorations' },
  { id: 12, name: 'Water', color: '#0ea5e9', category: 'decorations' },
  { id: 13, name: 'Plant', color: '#84cc16', category: 'furniture' },
  { id: 14, name: 'Collision', color: '#e11d48', category: 'collision' },
  { id: 15, name: 'Special', color: '#a855f7', category: 'decorations' },
  { id: 16, name: 'Station', color: '#0d9488', category: 'furniture' },
];

interface TilePaletteProps {
  selectedTile: number;
  selectedLayer: string;
  onTileSelect: (tileId: number) => void;
  onLayerSelect: (layer: string) => void;
  onErase: () => void;
}

export const TilePalette: FC<TilePaletteProps> = ({
  selectedTile,
  selectedLayer,
  onTileSelect,
  onLayerSelect,
  onErase,
}) => {
  return (
    <div className="w-44 bg-slate-900/95 border-r border-slate-700 flex flex-col overflow-y-auto">
      {/* Layer selector */}
      <div className="p-2 border-b border-slate-700">
        <h3 className="text-[8px] uppercase tracking-wider text-indigo-400 mb-1.5 font-mono">
          Layer
        </h3>
        <select
          value={selectedLayer}
          onChange={(e) => onLayerSelect(e.target.value)}
          className="w-full bg-slate-800 text-slate-300 text-[9px] px-2 py-1 rounded border border-slate-600 font-mono focus:outline-none focus:border-indigo-500"
          data-testid="layer-selector"
        >
          {LAYERS.map((l) => (
            <option key={l} value={l}>
              {l.toUpperCase()}
            </option>
          ))}
        </select>
      </div>

      {/* Eraser */}
      <div className="p-2 border-b border-slate-700">
        <button
          onClick={onErase}
          className={`w-full px-2 py-1.5 text-[9px] font-mono rounded transition-colors ${
            selectedTile === 0
              ? 'bg-red-600 text-white'
              : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
          }`}
          data-testid="eraser-button"
        >
          Eraser
        </button>
      </div>

      {/* Tile grid */}
      <div className="p-2 flex-1">
        <h3 className="text-[8px] uppercase tracking-wider text-indigo-400 mb-1.5 font-mono">
          Tiles
        </h3>
        <div className="grid grid-cols-4 gap-1">
          {TILE_DEFS.map((tile) => (
            <button
              key={tile.id}
              onClick={() => onTileSelect(tile.id)}
              className={`w-8 h-8 rounded border transition-all ${
                selectedTile === tile.id
                  ? 'border-indigo-400 ring-1 ring-indigo-400 scale-110'
                  : 'border-slate-600 hover:border-slate-400'
              }`}
              style={{ backgroundColor: tile.color }}
              title={tile.name}
              aria-label={`Select tile: ${tile.name}`}
            />
          ))}
        </div>
      </div>

      {/* Selected tile preview */}
      <div className="p-2 border-t border-slate-700">
        <div className="text-[8px] text-slate-500 font-mono mb-1">SELECTED</div>
        <div className="flex items-center gap-2">
          <div
            className="w-8 h-8 rounded border border-slate-600"
            style={{
              backgroundColor:
                selectedTile === 0
                  ? 'transparent'
                  : (TILE_DEFS.find((t) => t.id === selectedTile)?.color ?? '#4b5563'),
              backgroundImage: selectedTile === 0
                ? 'repeating-conic-gradient(#64748b 0% 25%, transparent 0% 50%)'
                : undefined,
              backgroundSize: selectedTile === 0 ? '8px 8px' : undefined,
            }}
          />
          <span className="text-[8px] text-slate-400 font-mono">
            {selectedTile === 0
              ? 'Eraser'
              : (TILE_DEFS.find((t) => t.id === selectedTile)?.name ?? `Tile #${selectedTile}`)}
          </span>
        </div>
      </div>
    </div>
  );
};
