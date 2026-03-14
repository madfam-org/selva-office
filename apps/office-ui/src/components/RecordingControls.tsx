'use client';

import { type FC } from 'react';

interface RecordingControlsProps {
  recordingState: 'idle' | 'recording' | 'processing';
  formattedDuration: string;
  onStart: () => void;
  onStop: () => void;
  visible: boolean;
}

export const RecordingControls: FC<RecordingControlsProps> = ({
  recordingState,
  formattedDuration,
  onStart,
  onStop,
  visible,
}) => {
  if (!visible) return null;

  return (
    <div className="absolute top-28 left-52 z-video flex items-center gap-2">
      {recordingState === 'idle' && (
        <button
          onClick={onStart}
          className="rounded px-2 py-1 text-xs font-mono bg-slate-700/80 text-slate-400 hover:bg-slate-600 transition-colors"
          title="Start Recording"
          aria-label="Start recording"
        >
          REC
        </button>
      )}

      {recordingState === 'recording' && (
        <button
          onClick={onStop}
          className="rounded px-2 py-1 text-xs font-mono bg-red-900/80 text-red-300 hover:bg-red-800 transition-colors flex items-center gap-1.5 animate-pulse-border"
          title="Stop Recording"
          aria-label="Stop recording"
        >
          <span className="inline-block h-2 w-2 rounded-full bg-red-500 animate-pulse" />
          {formattedDuration}
        </button>
      )}

      {recordingState === 'processing' && (
        <span className="rounded px-2 py-1 text-xs font-mono bg-slate-700/80 text-amber-400">
          Saving...
        </span>
      )}
    </div>
  );
};
