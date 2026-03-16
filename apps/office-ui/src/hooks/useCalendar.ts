'use client';

import { useState, useCallback, useEffect, useRef } from 'react';
import { apiFetch, isDemo } from '@/lib/api';

export interface CalendarEvent {
  id: string;
  title: string;
  start: string;
  end: string;
  is_all_day: boolean;
  meeting_url: string | null;
  organizer: string;
  attendees: string[];
  provider: string;
}

export type CalendarStatus = 'idle' | 'connecting' | 'connected' | 'error';

export interface UseCalendarReturn {
  events: CalendarEvent[];
  isBusy: boolean;
  connected: boolean;
  status: CalendarStatus;
  error: string | null;
  connect: (provider: 'google' | 'microsoft', accessToken: string, refreshToken?: string) => Promise<boolean>;
  disconnect: () => Promise<boolean>;
  refresh: () => Promise<void>;
}

const POLL_INTERVAL_MS = 60_000;

export function useCalendar(options?: {
  onBusyChange?: (busy: boolean) => void;
}): UseCalendarReturn {
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [isBusy, setIsBusy] = useState(false);
  const [connected, setConnected] = useState(false);
  const [status, setStatus] = useState<CalendarStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  const onBusyChangeRef = useRef(options?.onBusyChange);
  onBusyChangeRef.current = options?.onBusyChange;
  const prevBusyRef = useRef(false);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await apiFetch('/api/v1/calendar/status');
      if (res.ok) {
        const data = (await res.json()) as { connected: boolean; provider: string | null };
        setConnected(data.connected);
        if (data.connected) {
          setStatus('connected');
        }
      }
    } catch {
      // Silently ignore status check failures
    }
  }, []);

  const fetchEvents = useCallback(async () => {
    try {
      const res = await apiFetch('/api/v1/calendar/events');
      if (res.ok) {
        const data = (await res.json()) as { events: CalendarEvent[]; is_busy: boolean };
        setEvents(data.events);
        setIsBusy(data.is_busy);

        // Fire callback when busy state changes
        if (data.is_busy !== prevBusyRef.current) {
          prevBusyRef.current = data.is_busy;
          onBusyChangeRef.current?.(data.is_busy);
        }
      }
    } catch {
      // Silently ignore event fetch failures
    }
  }, []);

  const refresh = useCallback(async () => {
    await fetchEvents();
  }, [fetchEvents]);

  const connect = useCallback(async (
    provider: 'google' | 'microsoft',
    accessToken: string,
    refreshToken?: string,
  ): Promise<boolean> => {
    setStatus('connecting');
    setError(null);

    try {
      const res = await apiFetch('/api/v1/calendar/connect', {
        method: 'POST',
        body: JSON.stringify({
          provider,
          access_token: accessToken,
          refresh_token: refreshToken ?? null,
        }),
      });

      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as Record<string, unknown>;
        const detail = typeof body.detail === 'string' ? body.detail : `Connection failed (${res.status})`;
        setError(detail);
        setStatus('error');
        return false;
      }

      setConnected(true);
      setStatus('connected');
      await fetchEvents();
      return true;
    } catch {
      setError('Network error — could not reach server');
      setStatus('error');
      return false;
    }
  }, [fetchEvents]);

  const disconnect = useCallback(async (): Promise<boolean> => {
    try {
      const res = await apiFetch('/api/v1/calendar/disconnect', {
        method: 'DELETE',
      });

      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as Record<string, unknown>;
        const detail = typeof body.detail === 'string' ? body.detail : `Disconnect failed (${res.status})`;
        setError(detail);
        return false;
      }

      setConnected(false);
      setStatus('idle');
      setEvents([]);
      setIsBusy(false);
      prevBusyRef.current = false;
      return true;
    } catch {
      setError('Network error — could not reach server');
      return false;
    }
  }, []);

  // Check connection status on mount (skip in demo)
  const demo = isDemo();
  useEffect(() => {
    if (demo) return;
    void fetchStatus();
  }, [fetchStatus, demo]);

  // Poll events every 60s when connected (skip in demo)
  useEffect(() => {
    if (!connected || demo) return;

    // Fetch immediately, then start interval
    void fetchEvents();

    const interval = setInterval(() => {
      void fetchEvents();
    }, POLL_INTERVAL_MS);

    return () => clearInterval(interval);
  }, [connected, fetchEvents]);

  return {
    events,
    isBusy,
    connected,
    status,
    error,
    connect,
    disconnect,
    refresh,
  };
}
