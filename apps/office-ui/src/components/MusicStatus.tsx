'use client';

import { useState, useRef, useEffect, type FC } from 'react';

const MOOD_PRESETS = [
  '\u{1F3B5} Working',
  '\u{1F3A7} In the zone',
  '\u2615 Coffee break',
  '\u{1F914} Thinking',
  '\u{1F4BB} Coding',
  '\u{1F4DA} Reading',
];

const MAX_STATUS_LENGTH = 50;

interface MusicStatusProps {
  currentStatus: string;
  onStatusChange: (status: string) => void;
}

export const MusicStatus: FC<MusicStatusProps> = ({ currentStatus, onStatusChange }) => {
  const [editing, setEditing] = useState(false);
  const [input, setInput] = useState(currentStatus);
  const ref = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setEditing(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  // Sync input when external currentStatus changes
  useEffect(() => {
    if (!editing) {
      setInput(currentStatus);
    }
  }, [currentStatus, editing]);

  // Focus the input when editing starts
  useEffect(() => {
    if (editing) {
      inputRef.current?.focus();
    }
  }, [editing]);

  const handleSubmit = () => {
    const trimmed = input.trim().slice(0, MAX_STATUS_LENGTH);
    onStatusChange(trimmed);
    setEditing(false);
  };

  const handlePreset = (preset: string) => {
    setInput(preset);
    onStatusChange(preset);
    setEditing(false);
  };

  const handleClear = () => {
    setInput('');
    onStatusChange('');
    setEditing(false);
  };

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setEditing(!editing)}
        className="retro-panel flex items-center gap-2 px-3 py-1.5 font-mono text-[8px] cursor-pointer hover:bg-slate-700/50 transition-colors w-full text-left"
        aria-label={currentStatus ? `Music status: ${currentStatus}. Click to change.` : 'Set music status'}
      >
        <span className="text-slate-400 truncate max-w-[120px]">
          {currentStatus || '\u{1F3B5} Set status...'}
        </span>
      </button>

      {editing && (
        <div className="absolute left-0 top-full mt-1 z-modal retro-panel p-2 min-w-[180px] animate-fade-in">
          <div className="flex gap-1 mb-2">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value.slice(0, MAX_STATUS_LENGTH))}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleSubmit();
                if (e.key === 'Escape') setEditing(false);
              }}
              maxLength={MAX_STATUS_LENGTH}
              placeholder="What are you up to?"
              className="bg-slate-800 border border-slate-600 text-slate-200 text-[8px] font-mono px-2 py-1 rounded flex-1 min-w-0 focus:border-indigo-400 focus:outline-none"
              aria-label="Music status input"
            />
          </div>
          <div className="text-[7px] text-slate-500 mb-2 text-right">
            {input.length}/{MAX_STATUS_LENGTH}
          </div>
          <div className="flex flex-wrap gap-1 mb-2">
            {MOOD_PRESETS.map((preset) => (
              <button
                key={preset}
                onClick={() => handlePreset(preset)}
                className="text-[7px] font-mono bg-slate-700/50 hover:bg-slate-600/50 text-slate-300 px-2 py-1 rounded transition-colors"
              >
                {preset}
              </button>
            ))}
          </div>
          <div className="flex gap-1">
            <button
              onClick={handleSubmit}
              className="text-[7px] font-mono bg-indigo-600 hover:bg-indigo-500 text-white px-2 py-1 rounded transition-colors flex-1"
            >
              Set
            </button>
            {currentStatus && (
              <button
                onClick={handleClear}
                className="text-[7px] font-mono bg-slate-700 hover:bg-slate-600 text-slate-300 px-2 py-1 rounded transition-colors"
              >
                Clear
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
