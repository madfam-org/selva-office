'use client';

import { type FC, useState } from 'react';

interface RoomNavigatorProps {
  currentRoom: string;
  onChangeRoom: (roomId: string) => void;
  visible: boolean;
}

const AVAILABLE_ROOMS = [
  { id: 'office', label: 'Main Office', map: 'office-default' },
  { id: 'lounge', label: 'Lounge', map: 'lounge' },
  { id: 'conference', label: 'Conference Hall', map: 'conference' },
  { id: 'rooftop', label: 'Rooftop', map: 'rooftop' },
];

export const RoomNavigator: FC<RoomNavigatorProps> = ({
  currentRoom,
  onChangeRoom,
  visible,
}) => {
  const [open, setOpen] = useState(false);

  if (!visible) return null;

  return (
    <div className="absolute bottom-4 right-4 z-hud">
      <button
        onClick={() => setOpen(!open)}
        className="retro-panel px-3 py-2 font-mono text-[8px] text-slate-400 cursor-pointer hover:bg-slate-700/50 transition-colors"
        aria-label="Open room navigator"
      >
        ROOMS
      </button>

      {open && (
        <div className="absolute bottom-full right-0 mb-1 retro-panel py-1 min-w-[140px] animate-fade-in">
          {AVAILABLE_ROOMS.map((room) => (
            <button
              key={room.id}
              onClick={() => {
                if (room.id !== currentRoom) {
                  onChangeRoom(room.id);
                }
                setOpen(false);
              }}
              className={`flex w-full items-center gap-2 px-3 py-1.5 text-[8px] font-mono hover:bg-slate-700/50 transition-colors ${
                room.id === currentRoom ? 'text-indigo-400 bg-slate-700/30' : 'text-slate-400'
              }`}
              disabled={room.id === currentRoom}
            >
              {room.id === currentRoom && (
                <span className="inline-block h-1.5 w-1.5 rounded-full bg-indigo-400" />
              )}
              <span>{room.label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
