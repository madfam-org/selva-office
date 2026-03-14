'use client';

import { useCallback, type FC } from 'react';
import type { EditorObject } from './map-converter';

interface MapPropertiesProps {
  selectedObject: EditorObject | null;
  onObjectUpdate: (id: string, updates: Partial<EditorObject>) => void;
  onObjectRemove: (id: string) => void;
}

const INTERACTABLE_TYPES = [
  'dispatch',
  'blueprint',
  'url',
  'popup',
  'jitsi-zone',
  'silent-zone',
  'desk',
  'restricted-zone',
  'room-transition',
] as const;

export const MapProperties: FC<MapPropertiesProps> = ({
  selectedObject,
  onObjectUpdate,
  onObjectRemove,
}) => {
  const handlePropertyChange = useCallback(
    (key: string, value: string | number | boolean) => {
      if (!selectedObject) return;
      onObjectUpdate(selectedObject.id, {
        properties: { ...selectedObject.properties, [key]: value },
      });
    },
    [selectedObject, onObjectUpdate],
  );

  const handlePositionChange = useCallback(
    (field: 'x' | 'y' | 'width' | 'height', value: number) => {
      if (!selectedObject) return;
      onObjectUpdate(selectedObject.id, { [field]: value });
    },
    [selectedObject, onObjectUpdate],
  );

  if (!selectedObject) {
    return (
      <div className="w-52 bg-slate-900/95 border-l border-slate-700 flex flex-col">
        <div className="p-2 border-b border-slate-700">
          <h3 className="text-[8px] uppercase tracking-wider text-indigo-400 font-mono">
            Properties
          </h3>
        </div>
        <div className="p-3 text-[8px] text-slate-500 font-mono">
          Select an object to edit its properties.
        </div>
      </div>
    );
  }

  const inputClass =
    'w-full bg-slate-800 text-slate-200 text-[9px] px-2 py-1 rounded border border-slate-600 font-mono focus:outline-none focus:border-indigo-500';
  const labelClass = 'text-[7px] uppercase tracking-wider text-slate-400 font-mono mb-0.5';

  return (
    <div className="w-52 bg-slate-900/95 border-l border-slate-700 flex flex-col overflow-y-auto">
      <div className="p-2 border-b border-slate-700">
        <h3 className="text-[8px] uppercase tracking-wider text-indigo-400 font-mono">
          Properties
        </h3>
      </div>

      <div className="p-2 space-y-2">
        {/* Type badge */}
        <div>
          <div className={labelClass}>Type</div>
          <div className="text-[9px] text-cyan-400 font-mono bg-slate-800 px-2 py-1 rounded">
            {selectedObject.type}
          </div>
        </div>

        {/* Position / Size */}
        <div className="grid grid-cols-2 gap-1">
          <div>
            <div className={labelClass}>X</div>
            <input
              type="number"
              value={selectedObject.x}
              onChange={(e) => handlePositionChange('x', Number(e.target.value))}
              className={inputClass}
            />
          </div>
          <div>
            <div className={labelClass}>Y</div>
            <input
              type="number"
              value={selectedObject.y}
              onChange={(e) => handlePositionChange('y', Number(e.target.value))}
              className={inputClass}
            />
          </div>
          <div>
            <div className={labelClass}>Width</div>
            <input
              type="number"
              value={selectedObject.width}
              onChange={(e) => handlePositionChange('width', Number(e.target.value))}
              className={inputClass}
            />
          </div>
          <div>
            <div className={labelClass}>Height</div>
            <input
              type="number"
              value={selectedObject.height}
              onChange={(e) => handlePositionChange('height', Number(e.target.value))}
              className={inputClass}
            />
          </div>
        </div>

        <div className="w-full h-px bg-slate-700" />

        {/* Dynamic property fields based on object type */}
        {selectedObject.type === 'department' && (
          <>
            <div>
              <div className={labelClass}>Name</div>
              <input
                type="text"
                value={(selectedObject.properties.name as string) ?? ''}
                onChange={(e) => handlePropertyChange('name', e.target.value)}
                className={inputClass}
              />
            </div>
            <div>
              <div className={labelClass}>Slug</div>
              <input
                type="text"
                value={(selectedObject.properties.slug as string) ?? ''}
                onChange={(e) => handlePropertyChange('slug', e.target.value)}
                className={inputClass}
              />
            </div>
            <div>
              <div className={labelClass}>Color</div>
              <input
                type="text"
                value={(selectedObject.properties.color as string) ?? ''}
                onChange={(e) => handlePropertyChange('color', e.target.value)}
                className={inputClass}
              />
            </div>
            <div>
              <div className={labelClass}>Max Agents</div>
              <input
                type="number"
                value={(selectedObject.properties.maxAgents as string) ?? '4'}
                onChange={(e) => handlePropertyChange('maxAgents', e.target.value)}
                className={inputClass}
              />
            </div>
          </>
        )}

        {selectedObject.type === 'review-station' && (
          <div>
            <div className={labelClass}>Department Slug</div>
            <input
              type="text"
              value={(selectedObject.properties.departmentSlug as string) ?? ''}
              onChange={(e) => handlePropertyChange('departmentSlug', e.target.value)}
              className={inputClass}
            />
          </div>
        )}

        {selectedObject.type === 'interactable' && (
          <>
            <div>
              <div className={labelClass}>Interact Type</div>
              <select
                value={(selectedObject.properties.interactType as string) ?? 'dispatch'}
                onChange={(e) => handlePropertyChange('interactType', e.target.value)}
                className={inputClass}
              >
                {INTERACTABLE_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <div className={labelClass}>Label</div>
              <input
                type="text"
                value={(selectedObject.properties.label as string) ?? ''}
                onChange={(e) => handlePropertyChange('label', e.target.value)}
                className={inputClass}
              />
            </div>
            <div>
              <div className={labelClass}>Content</div>
              <input
                type="text"
                value={(selectedObject.properties.content as string) ?? ''}
                onChange={(e) => handlePropertyChange('content', e.target.value)}
                className={inputClass}
                placeholder="URL, text, room ID..."
              />
            </div>
          </>
        )}

        {selectedObject.type === 'spawn-point' && (
          <div>
            <div className={labelClass}>Name</div>
            <input
              type="text"
              value={(selectedObject.properties.name as string) ?? ''}
              onChange={(e) => handlePropertyChange('name', e.target.value)}
              className={inputClass}
            />
          </div>
        )}

        <div className="w-full h-px bg-slate-700" />

        {/* Delete button */}
        <button
          onClick={() => onObjectRemove(selectedObject.id)}
          className="w-full px-2 py-1.5 text-[8px] font-mono rounded bg-red-900/50 text-red-300 hover:bg-red-800 transition-colors"
        >
          Delete Object
        </button>
      </div>
    </div>
  );
};
