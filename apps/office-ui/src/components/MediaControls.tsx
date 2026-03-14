'use client';

import { useEffect } from 'react';

interface MediaControlsProps {
  audioEnabled: boolean;
  videoEnabled: boolean;
  onToggleAudio: () => void;
  onToggleVideo: () => void;
  screenSharing?: boolean;
  onToggleScreenShare?: () => void;
  bubbleLocked?: boolean;
  onToggleLockBubble?: () => void;
  visible: boolean;
}

/**
 * Mute (M) and camera (V) toggle buttons.
 * Positioned at top-left below the video bubbles.
 */
export function MediaControls({
  audioEnabled,
  videoEnabled,
  onToggleAudio,
  onToggleVideo,
  screenSharing,
  onToggleScreenShare,
  bubbleLocked,
  onToggleLockBubble,
  visible,
}: MediaControlsProps) {
  // Keyboard shortcuts: M for mute, V for camera
  useEffect(() => {
    if (!visible) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't intercept if typing in an input
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement
      )
        return;

      if (e.key === 'm' || e.key === 'M') {
        onToggleAudio();
      }
      if (e.key === 'v' || e.key === 'V') {
        onToggleVideo();
      }
      if ((e.key === 's' || e.key === 'S') && onToggleScreenShare) {
        onToggleScreenShare();
      }
      if ((e.key === 'l' || e.key === 'L') && onToggleLockBubble) {
        onToggleLockBubble();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [visible, onToggleAudio, onToggleVideo, onToggleScreenShare, onToggleLockBubble]);

  if (!visible) return null;

  return (
    <div className="absolute top-28 left-4 z-video flex gap-2">
      <button
        onClick={onToggleAudio}
        className={`rounded px-2 py-1 text-xs font-mono transition-colors ${
          audioEnabled
            ? 'bg-slate-700/80 text-green-400 hover:bg-slate-600'
            : 'bg-red-900/80 text-red-300 hover:bg-red-800'
        }`}
        title={audioEnabled ? 'Mute (M)' : 'Unmute (M)'}
        aria-label={audioEnabled ? 'Mute microphone' : 'Unmute microphone'}
      >
        {audioEnabled ? 'MIC ON' : 'MIC OFF'}
      </button>

      <button
        onClick={onToggleVideo}
        className={`rounded px-2 py-1 text-xs font-mono transition-colors ${
          videoEnabled
            ? 'bg-slate-700/80 text-green-400 hover:bg-slate-600'
            : 'bg-red-900/80 text-red-300 hover:bg-red-800'
        }`}
        title={videoEnabled ? 'Camera Off (V)' : 'Camera On (V)'}
        aria-label={videoEnabled ? 'Turn camera off' : 'Turn camera on'}
      >
        {videoEnabled ? 'CAM ON' : 'CAM OFF'}
      </button>

      {onToggleScreenShare && (
        <button
          onClick={onToggleScreenShare}
          className={`rounded px-2 py-1 text-xs font-mono transition-colors ${
            screenSharing
              ? 'bg-indigo-900/80 text-indigo-300 hover:bg-indigo-800'
              : 'bg-slate-700/80 text-slate-400 hover:bg-slate-600'
          }`}
          title={screenSharing ? 'Stop Sharing (S)' : 'Share Screen (S)'}
          aria-label={screenSharing ? 'Stop screen sharing' : 'Start screen sharing'}
        >
          {screenSharing ? 'SHARING' : 'SCREEN'}
        </button>
      )}

      {onToggleLockBubble && (
        <button
          onClick={onToggleLockBubble}
          className={`rounded px-2 py-1 text-xs font-mono transition-colors ${
            bubbleLocked
              ? 'bg-amber-900/80 text-amber-300 hover:bg-amber-800'
              : 'bg-slate-700/80 text-slate-400 hover:bg-slate-600'
          }`}
          title={bubbleLocked ? 'Unlock Bubble (L)' : 'Lock Bubble (L)'}
          aria-label={bubbleLocked ? 'Unlock proximity bubble' : 'Lock proximity bubble'}
        >
          {bubbleLocked ? 'LOCKED' : 'LOCK'}
        </button>
      )}
    </div>
  );
}
