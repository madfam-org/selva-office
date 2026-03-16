'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import type { TaskEvent, EventCategory } from '@autoswarm/shared-types';
import { apiFetch } from '@/lib/api';

const WS_URL =
  process.env.NEXT_PUBLIC_EVENTS_WS_URL ?? 'ws://localhost:4300/api/v1/events/ws';
const MAX_RECONNECT_DELAY_MS = 30000;
const MAX_IN_MEMORY = 500;

export interface EventFilters {
  eventCategory: EventCategory | null;
  eventType: string | null;
  taskId: string | null;
  agentId: string | null;
  searchQuery: string;
}

interface EventStreamState {
  events: TaskEvent[];
  connected: boolean;
  filters: EventFilters;
  setFilters: (filters: Partial<EventFilters>) => void;
  loadMore: () => Promise<void>;
  hasMore: boolean;
  loading: boolean;
}

/**
 * React hook for the real-time event stream.
 * Connects to the nexus-api events WebSocket, listens for task_event messages,
 * and provides filtering and pagination.
 */
export function useEventStream(): EventStreamState {
  const [allEvents, setAllEvents] = useState<TaskEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [loading, setLoading] = useState(false);
  const [filters, setFiltersState] = useState<EventFilters>({
    eventCategory: null,
    eventType: null,
    taskId: null,
    agentId: null,
    searchQuery: '',
  });
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttempts = useRef(0);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    try {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        reconnectAttempts.current = 0;
      };

      ws.onmessage = (event: MessageEvent) => {
        try {
          const message = JSON.parse(event.data as string);

          switch (message.type) {
            case 'event_batch': {
              const batch = message.payload as TaskEvent[];
              setAllEvents(batch);
              break;
            }
            case 'task_event': {
              const taskEvent = message.payload as TaskEvent;
              setAllEvents((prev) => {
                // Avoid duplicates
                if (prev.some((e) => e.id === taskEvent.id)) return prev;
                const next = [taskEvent, ...prev];
                return next.length > MAX_IN_MEMORY ? next.slice(0, MAX_IN_MEMORY) : next;
              });
              break;
            }
            case 'pong':
              break;
          }
        } catch {
          // Ignore malformed messages
        }
      };

      ws.onclose = (event: CloseEvent) => {
        setConnected(false);
        wsRef.current = null;

        if (event.code !== 1000) {
          reconnectAttempts.current++;
          const delay =
            Math.min(MAX_RECONNECT_DELAY_MS, 1000 * Math.pow(2, reconnectAttempts.current)) +
            Math.random() * 1000;
          reconnectTimer.current = setTimeout(connect, delay);
        }
      };

      ws.onerror = () => {
        setConnected(false);
      };
    } catch {
      setConnected(false);
      reconnectAttempts.current++;
      const delay =
        Math.min(MAX_RECONNECT_DELAY_MS, 1000 * Math.pow(2, reconnectAttempts.current)) +
        Math.random() * 1000;
      reconnectTimer.current = setTimeout(connect, delay);
    }
  }, []);

  useEffect(() => {
    connect();

    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (wsRef.current) {
        wsRef.current.close(1000, 'Component unmounted');
        wsRef.current = null;
      }
    };
  }, [connect]);

  const loadMore = useCallback(async () => {
    if (loading || !hasMore) return;
    setLoading(true);
    try {
      const params = new URLSearchParams({
        limit: '50',
        offset: String(allEvents.length),
      });
      const res = await apiFetch(`/api/v1/events?${params}`);
      if (res.ok) {
        const older = (await res.json()) as TaskEvent[];
        if (older.length < 50) setHasMore(false);
        setAllEvents((prev) => {
          const ids = new Set(prev.map((e) => e.id));
          const deduped = older.filter((e) => !ids.has(e.id));
          return [...prev, ...deduped];
        });
      }
    } catch {
      // Silently fail
    } finally {
      setLoading(false);
    }
  }, [allEvents.length, loading, hasMore]);

  const setFilters = useCallback((partial: Partial<EventFilters>) => {
    setFiltersState((prev) => ({ ...prev, ...partial }));
  }, []);

  // Apply client-side filters
  const events = allEvents.filter((e) => {
    if (filters.eventCategory && e.event_category !== filters.eventCategory) return false;
    if (filters.eventType && e.event_type !== filters.eventType) return false;
    if (filters.taskId && e.task_id !== filters.taskId) return false;
    if (filters.agentId && e.agent_id !== filters.agentId) return false;
    if (filters.searchQuery) {
      const q = filters.searchQuery.toLowerCase();
      const searchable = [
        e.event_type,
        e.node_id,
        e.provider,
        e.model,
        e.error_message,
        e.graph_type,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      if (!searchable.includes(q)) return false;
    }
    return true;
  });

  return { events, connected, filters, setFilters, loadMore, hasMore, loading };
}
