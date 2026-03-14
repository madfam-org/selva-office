'use client';

import { type FC } from 'react';

interface MegaphoneControlsProps {
  active: boolean;
  speakerName: string | null;
  isLocalSpeaker: boolean;
  onStart: () => void;
  onStop: () => void;
  visible: boolean;
}

export const MegaphoneControls: FC<MegaphoneControlsProps> = ({
  active,
  speakerName,
  isLocalSpeaker,
  onStart,
  onStop,
  visible,
}) => {
  if (!visible) return null;

  return (
    <div className="absolute top-36 left-4 z-video flex items-center gap-2">
      {!active && (
        <button
          onClick={onStart}
          className="rounded px-2 py-1 text-xs font-mono bg-slate-700/80 text-slate-400 hover:bg-slate-600 transition-colors"
          title="Start Megaphone"
          aria-label="Start megaphone broadcast"
        >
          MEGAPHONE
        </button>
      )}

      {active && isLocalSpeaker && (
        <button
          onClick={onStop}
          className="rounded px-2 py-1 text-xs font-mono bg-amber-900/80 text-amber-300 hover:bg-amber-800 transition-colors flex items-center gap-1.5 animate-pulse-border"
          title="Stop Megaphone"
          aria-label="Stop megaphone broadcast"
        >
          <span className="inline-block h-2 w-2 rounded-full bg-amber-400 animate-pulse" />
          BROADCASTING
        </button>
      )}

      {active && !isLocalSpeaker && speakerName && (
        <span className="rounded px-2 py-1 text-xs font-mono bg-slate-700/80 text-amber-400">
          {speakerName} is broadcasting
        </span>
      )}
    </div>
  );
};
