'use client';

import { type FC } from 'react';

interface SpotlightControlsProps {
  active: boolean;
  presenterName: string | null;
  isPresenting: boolean;
  onStart: () => void;
  onStop: () => void;
  visible: boolean;
}

export const SpotlightControls: FC<SpotlightControlsProps> = ({
  active,
  presenterName,
  isPresenting,
  onStart,
  onStop,
  visible,
}) => {
  if (!visible) return null;

  return (
    <div className="absolute top-44 left-4 z-video flex items-center gap-2">
      {!active && (
        <button
          onClick={onStart}
          className="rounded px-2 py-1 text-xs font-mono bg-slate-700/80 text-slate-400 hover:bg-slate-600 transition-colors"
          title="Start Spotlight Presentation"
          aria-label="Start spotlight presentation"
        >
          SPOTLIGHT
        </button>
      )}

      {active && isPresenting && (
        <button
          onClick={onStop}
          className="rounded px-2 py-1 text-xs font-mono bg-violet-900/80 text-violet-300 hover:bg-violet-800 transition-colors flex items-center gap-1.5 animate-pulse-border"
          title="Stop Spotlight"
          aria-label="Stop spotlight presentation"
        >
          <span className="inline-block h-2 w-2 rounded-full bg-violet-400 animate-pulse" />
          PRESENTING
        </button>
      )}

      {active && !isPresenting && presenterName && (
        <span className="rounded px-2 py-1 text-xs font-mono bg-slate-700/80 text-violet-400">
          {presenterName} is presenting
        </span>
      )}
    </div>
  );
};
