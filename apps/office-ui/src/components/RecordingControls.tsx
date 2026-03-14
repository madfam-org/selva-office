'use client';

import { type FC } from 'react';

interface RecordingControlsProps {
  recordingState: 'idle' | 'recording' | 'processing';
  formattedDuration: string;
  onStart: () => void;
  onStop: () => void;
  visible: boolean;
  lastRecordingUrl?: string | null;
  onGenerateNotes?: () => void;
}

export const RecordingControls: FC<RecordingControlsProps> = ({
  recordingState,
  formattedDuration,
  onStart,
  onStop,
  visible,
  lastRecordingUrl,
  onGenerateNotes,
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

      {recordingState === 'idle' && lastRecordingUrl && onGenerateNotes && (
        <button
          onClick={onGenerateNotes}
          className="rounded px-2 py-1 text-xs font-mono bg-indigo-700/80 text-indigo-200 hover:bg-indigo-600 transition-colors"
          title="Generate meeting notes from last recording"
          aria-label="Generate meeting notes"
        >
          Notes
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
