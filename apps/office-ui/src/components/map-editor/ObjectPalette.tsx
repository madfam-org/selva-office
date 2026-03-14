'use client';

import { type FC, useCallback } from 'react';
import type { EditorObject } from './map-converter';

const OBJECT_CATEGORIES = [
  {
    name: 'Departments',
    items: [
      { type: 'department' as const, label: 'Department Zone', defaults: { name: 'Engineering', slug: 'engineering', color: '#6366f1', maxAgents: '4' } },
    ],
  },
  {
    name: 'Stations',
    items: [
      { type: 'review-station' as const, label: 'Review Station', defaults: { departmentSlug: 'engineering' } },
    ],
  },
  {
    name: 'Interactables',
    items: [
      { type: 'interactable' as const, label: 'Dispatch Station', defaults: { interactType: 'dispatch', label: 'Dispatch Task' } },
      { type: 'interactable' as const, label: 'Blueprint Desk', defaults: { interactType: 'blueprint', label: 'Blueprint Lab' } },
      { type: 'interactable' as const, label: 'URL Link', defaults: { interactType: 'url', content: 'https://example.com', label: 'External Link' } },
      { type: 'interactable' as const, label: 'Popup', defaults: { interactType: 'popup', content: 'Hello!', label: 'Info' } },
      { type: 'interactable' as const, label: 'Silent Zone', defaults: { interactType: 'silent-zone', label: 'Quiet Area' } },
      { type: 'interactable' as const, label: 'Desk', defaults: { interactType: 'desk', label: 'Desk', assignedAgentId: '' } },
      { type: 'interactable' as const, label: 'Restricted Zone', defaults: { interactType: 'restricted-zone', requiredTags: '', label: 'Restricted' } },
      { type: 'interactable' as const, label: 'Room Transition', defaults: { interactType: 'room-transition', content: 'office', label: 'Go to Room' } },
    ],
  },
  {
    name: 'Spawn Points',
    items: [
      { type: 'spawn-point' as const, label: 'Player Spawn', defaults: { name: 'player-spawn' } },
    ],
  },
] as const;

let objectIdCounter = 0;

interface ObjectPaletteProps {
  onPlaceObject: (obj: EditorObject) => void;
  onPushUndo: (label: string) => void;
}

export const ObjectPalette: FC<ObjectPaletteProps> = ({ onPlaceObject, onPushUndo }) => {
  const handleClick = useCallback(
    (type: EditorObject['type'], defaults: Record<string, string>) => {
      onPushUndo('place object');
      const obj: EditorObject = {
        id: `obj_${++objectIdCounter}_${Date.now()}`,
        type,
        x: 160, // center-ish default position (pixels)
        y: 160,
        width: type === 'department' ? 256 : 32,
        height: type === 'department' ? 192 : 32,
        properties: { ...defaults },
      };
      onPlaceObject(obj);
    },
    [onPlaceObject, onPushUndo],
  );

  return (
    <div className="w-44 bg-slate-900/95 border-l border-slate-700 flex flex-col overflow-y-auto">
      <div className="p-2 border-b border-slate-700">
        <h3 className="text-[8px] uppercase tracking-wider text-indigo-400 font-mono">
          Objects
        </h3>
      </div>

      {OBJECT_CATEGORIES.map((cat) => (
        <div key={cat.name} className="p-2 border-b border-slate-800">
          <div className="text-[7px] uppercase tracking-wider text-slate-500 mb-1 font-mono">
            {cat.name}
          </div>
          <div className="flex flex-col gap-1">
            {cat.items.map((item, idx) => (
              <button
                key={`${item.type}-${idx}`}
                onClick={() => handleClick(item.type, item.defaults as Record<string, string>)}
                className="px-2 py-1.5 bg-slate-800 text-[8px] text-slate-300 font-mono rounded hover:bg-slate-700 transition-colors text-left truncate"
                title={item.label}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
};
