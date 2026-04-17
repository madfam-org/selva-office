'use client';

import { useEffect, useRef, type FC } from 'react';
import { useEventStream } from '@/hooks/useEventStream';
import type { EventCategory, TaskEvent } from '@selva/shared-types';

interface OpsFeedProps {
  open: boolean;
  onClose: () => void;
}

const CATEGORY_COLORS: Record<EventCategory, string> = {
  task: 'border-l-blue-500',
  node: 'border-l-cyan-500',
  llm: 'border-l-purple-500',
  approval: 'border-l-amber-500',
  git: 'border-l-green-500',
  permission: 'border-l-rose-500',
  webhook: 'border-l-orange-500',
  system: 'border-l-slate-500',
};

const CATEGORY_LABELS: Record<EventCategory, string> = {
  task: 'Task',
  node: 'Node',
  llm: 'LLM',
  approval: 'Approval',
  git: 'Git',
  permission: 'Perm',
  webhook: 'Hook',
  system: 'Sys',
};

const ALL_CATEGORIES: EventCategory[] = [
  'task', 'node', 'llm', 'approval', 'git', 'webhook', 'system',
];

function formatDuration(ms: number | null): string {
  if (ms === null) return '';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return '';
  }
}

const EventCard: FC<{ event: TaskEvent }> = ({ event }) => {
  const borderColor = CATEGORY_COLORS[event.event_category as EventCategory] ?? 'border-l-slate-500';
  const isError = event.event_type.includes('error') || event.event_type.includes('failed') || event.event_type.includes('timeout');

  return (
    <div
      className={`border-l-2 ${borderColor} bg-slate-800/60 px-2 py-1.5 font-mono text-[8px] animate-fade-in-up`}
    >
      <div className="flex items-center justify-between gap-1">
        <span className={`font-bold ${isError ? 'text-red-400' : 'text-slate-200'}`}>
          {event.event_type}
        </span>
        <span className="text-slate-600">{formatTime(event.created_at)}</span>
      </div>

      <div className="mt-0.5 flex flex-wrap items-center gap-1 text-[7px]">
        {event.node_id && (
          <span className="rounded bg-cyan-900/40 px-1 text-cyan-400">{event.node_id}</span>
        )}
        {event.graph_type && (
          <span className="rounded bg-indigo-900/40 px-1 text-indigo-400">{event.graph_type}</span>
        )}
        {event.provider && (
          <span className="rounded bg-purple-900/40 px-1 text-purple-400">
            {event.provider}{event.model ? `/${event.model}` : ''}
          </span>
        )}
        {event.token_count != null && event.token_count > 0 && (
          <span className="text-purple-300">{event.token_count} tok</span>
        )}
        {event.duration_ms != null && (
          <span className="text-slate-400">{formatDuration(event.duration_ms)}</span>
        )}
      </div>

      {event.error_message && (
        <p className="mt-0.5 truncate text-red-400 text-[7px]">
          {event.error_message}
        </p>
      )}
    </div>
  );
};

export const OpsFeed: FC<OpsFeedProps> = ({ open, onClose }) => {
  const { events, connected, filters, setFilters, loadMore, hasMore, loading } = useEventStream();
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to top when new events arrive
  useEffect(() => {
    if (scrollRef.current && events.length > 0) {
      scrollRef.current.scrollTop = 0;
    }
  }, [events.length]);

  if (!open) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-[19] bg-black/20 animate-fade-in"
        onClick={onClose}
      />

      <aside
        className="absolute left-0 top-0 z-hud h-[60vh] sm:h-full w-[85vw] sm:w-80 max-w-80 rounded-b-xl sm:rounded-none landscape:max-h-[70vh] transform transition-transform duration-300 translate-x-0"
        aria-label="Operations feed"
        role="complementary"
      >
        <div className="flex h-full flex-col bg-slate-900/95 backdrop-blur-sm pixel-border-accent">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-slate-700 px-4 py-3">
            <h2 className="pixel-text text-[10px] uppercase tracking-wider text-emerald-400">
              Ops Feed
            </h2>
            <div className="flex items-center gap-2">
              <span className={`h-1.5 w-1.5 rounded-full ${connected ? 'bg-emerald-400' : 'bg-red-400'}`} />
              <button
                onClick={onClose}
                className="font-mono text-[10px] text-slate-500 hover:text-white"
                aria-label="Close ops feed"
              >
                X
              </button>
            </div>
          </div>

          {/* Category filter pills */}
          <div className="flex flex-wrap gap-1 border-b border-slate-800 px-3 py-2">
            <button
              onClick={() => setFilters({ eventCategory: null })}
              className={`px-2 py-0.5 font-mono text-[7px] uppercase ${
                !filters.eventCategory
                  ? 'bg-emerald-600 text-white'
                  : 'bg-slate-800 text-slate-400 hover:text-white'
              }`}
            >
              All
            </button>
            {ALL_CATEGORIES.map((cat) => (
              <button
                key={cat}
                onClick={() =>
                  setFilters({
                    eventCategory: filters.eventCategory === cat ? null : cat,
                  })
                }
                className={`px-2 py-0.5 font-mono text-[7px] uppercase ${
                  filters.eventCategory === cat
                    ? 'bg-emerald-600 text-white'
                    : 'bg-slate-800 text-slate-400 hover:text-white'
                }`}
              >
                {CATEGORY_LABELS[cat]}
              </button>
            ))}
          </div>

          {/* Search input */}
          <div className="border-b border-slate-800 px-3 py-2">
            <input
              type="text"
              placeholder="Search events..."
              aria-label="Search events"
              value={filters.searchQuery}
              onChange={(e) => setFilters({ searchQuery: e.target.value })}
              className="w-full bg-slate-800 px-2 py-1 font-mono text-[8px] text-slate-300 placeholder-slate-600 outline-none focus:ring-1 focus:ring-emerald-500"
            />
          </div>

          {/* Event list */}
          <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 py-2 space-y-1">
            {events.length === 0 ? (
              <p className="py-8 text-center font-mono text-[8px] text-slate-600 italic">
                No events yet
              </p>
            ) : (
              events.map((event) => <EventCard key={event.id} event={event} />)
            )}

            {hasMore && events.length > 0 && (
              <button
                onClick={() => void loadMore()}
                disabled={loading}
                className="w-full py-2 font-mono text-[8px] text-slate-500 hover:text-white disabled:opacity-50"
              >
                {loading ? 'Loading...' : 'Load more'}
              </button>
            )}
          </div>

          {/* Footer stats */}
          <div className="border-t border-slate-800 px-4 py-2 font-mono text-[7px] text-slate-600">
            {events.length} events shown
          </div>
        </div>
      </aside>
    </>
  );
};
