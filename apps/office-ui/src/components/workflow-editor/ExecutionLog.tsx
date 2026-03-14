'use client';

import { useRef, useEffect, useState } from 'react';
import type { ExecutionEvent } from '@/hooks/useExecutionLog';

interface ExecutionLogProps {
  events: ExecutionEvent[];
  onClear: () => void;
}

function formatTime(ts: number): string {
  const d = new Date(ts);
  return d.toLocaleTimeString('en-US', { hour12: false });
}

export function ExecutionLog({ events, onClear }: ExecutionLogProps) {
  const [collapsed, setCollapsed] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events]);

  return (
    <div className={`border-t border-slate-700 bg-slate-900/90 flex-shrink-0 transition-all ${collapsed ? 'h-8' : 'h-32'}`}>
      <div className="flex items-center justify-between px-3 py-1 border-b border-slate-800">
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="pixel-text text-retro-xs text-slate-400 hover:text-slate-300"
        >
          {collapsed ? '▸' : '▾'} EXECUTION LOG ({events.length})
        </button>
        {!collapsed && (
          <button
            onClick={onClear}
            className="pixel-text text-[6px] text-slate-500 hover:text-slate-400"
          >
            Clear
          </button>
        )}
      </div>
      {!collapsed && (
        <div ref={scrollRef} className="overflow-y-auto h-[calc(100%-24px)] px-3 py-1 space-y-0.5">
          {events.length === 0 ? (
            <p className="text-retro-xs text-slate-600 italic">No execution events yet</p>
          ) : (
            events.map((evt, i) => (
              <div key={i} className="flex items-center gap-2 text-retro-xs">
                <span className="text-slate-500 font-mono">[{formatTime(evt.timestamp)}]</span>
                <span className="text-slate-400">{evt.agentName}</span>
                <span className={evt.type === 'started' ? 'text-cyan-400' : 'text-green-400'}>
                  {evt.nodeId}
                </span>
                <span className="text-slate-500">{evt.type === 'started' ? 'started' : 'completed'}</span>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
