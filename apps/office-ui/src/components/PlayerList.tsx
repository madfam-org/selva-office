'use client';

import { useCallback } from 'react';
import { gameEventBus } from '@/game/PhaserGame';

interface Player {
  sessionId: string;
  name: string;
  status: string;
}

interface PlayerListProps {
  players: Player[];
  localSessionId: string;
  isOpen: boolean;
  onClose: () => void;
}

const STATUS_COLORS: Record<string, string> = {
  online: 'bg-green-400',
  away: 'bg-amber-400',
  busy: 'bg-red-400',
  dnd: 'bg-gray-400',
};

/**
 * Sliding panel listing connected players with Teleport and Follow buttons.
 */
export function PlayerList({ players, localSessionId, isOpen, onClose }: PlayerListProps) {
  const handleTeleport = useCallback(
    (targetSessionId: string) => {
      gameEventBus.dispatchEvent(
        new CustomEvent('teleport', { detail: { targetSessionId } })
      );
    },
    []
  );

  const handleFollow = useCallback(
    (targetSessionId: string) => {
      gameEventBus.dispatchEvent(
        new CustomEvent('follow-player', { detail: { targetSessionId } })
      );
    },
    []
  );

  if (!isOpen) return null;

  const remotePlayers = players.filter((p) => p.sessionId !== localSessionId);

  return (
    <div className="fixed right-0 top-0 h-full w-full max-w-72 sm:w-72 retro-panel z-modal animate-slide-in-right flex flex-col">
      <div className="flex items-center justify-between p-3 border-b border-slate-700">
        <h2 className="text-retro-base font-bold text-slate-200">
          Players ({remotePlayers.length})
        </h2>
        <button
          onClick={onClose}
          className="text-slate-400 hover:text-slate-200"
          aria-label="Close player list"
        >
          [X]
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {remotePlayers.length === 0 && (
          <p className="text-retro-xs text-slate-500 text-center py-4">
            No other players connected
          </p>
        )}

        {remotePlayers.map((player) => (
          <div
            key={player.sessionId}
            className="flex items-center justify-between p-2 rounded bg-slate-800/50 hover:bg-slate-700/50"
          >
            <div className="flex items-center gap-2 min-w-0">
              <span
                className={`w-2 h-2 rounded-full flex-shrink-0 ${STATUS_COLORS[player.status] || 'bg-slate-400'}`}
              />
              <span className="text-retro-xs text-slate-200 truncate">
                {player.name}
              </span>
            </div>

            <div className="flex gap-1 flex-shrink-0">
              <button
                onClick={() => handleTeleport(player.sessionId)}
                className="pxa-btn text-retro-xs px-2 py-0.5"
                title="Teleport to player"
              >
                Go
              </button>
              <button
                onClick={() => handleFollow(player.sessionId)}
                className="pxa-btn text-retro-xs px-2 py-0.5"
                title="Follow player"
              >
                Follow
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
