'use client';

import { useState, useEffect, useRef, useCallback } from 'react';

export type PlayerStatusType = 'online' | 'away' | 'busy' | 'dnd';

const AUTO_AWAY_MS = 5 * 60 * 1000; // 5 minutes

interface UsePlayerStatusOptions {
  sendStatus: (status: string) => void;
  enabled: boolean;
}

export function usePlayerStatus({ sendStatus, enabled }: UsePlayerStatusOptions) {
  const [status, setStatus] = useState<PlayerStatusType>('online');
  const lastActivityRef = useRef(Date.now());
  const autoAwayTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const wasAutoAway = useRef(false);

  const changeStatus = useCallback((newStatus: PlayerStatusType) => {
    setStatus(newStatus);
    if (enabled) {
      sendStatus(newStatus);
    }
    wasAutoAway.current = false;
  }, [sendStatus, enabled]);

  // Track user activity
  useEffect(() => {
    const onActivity = () => {
      lastActivityRef.current = Date.now();
      // If was auto-away, restore to online
      if (wasAutoAway.current) {
        wasAutoAway.current = false;
        setStatus('online');
        if (enabled) sendStatus('online');
      }
    };

    window.addEventListener('mousemove', onActivity);
    window.addEventListener('keydown', onActivity);
    window.addEventListener('pointerdown', onActivity);

    return () => {
      window.removeEventListener('mousemove', onActivity);
      window.removeEventListener('keydown', onActivity);
      window.removeEventListener('pointerdown', onActivity);
    };
  }, [sendStatus, enabled]);

  // Auto-away timer
  useEffect(() => {
    if (!enabled) return;

    autoAwayTimerRef.current = setInterval(() => {
      const idle = Date.now() - lastActivityRef.current;
      if (idle >= AUTO_AWAY_MS && status === 'online') {
        wasAutoAway.current = true;
        setStatus('away');
        sendStatus('away');
      }
    }, 30_000); // Check every 30 seconds

    return () => {
      if (autoAwayTimerRef.current) {
        clearInterval(autoAwayTimerRef.current);
      }
    };
  }, [sendStatus, enabled, status]);

  return { status, changeStatus };
}
