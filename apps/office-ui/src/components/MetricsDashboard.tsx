'use client';

import { useEffect, type FC } from 'react';
import { CloseButton } from '@selva/ui';
import { useMetrics, type MetricsPeriod } from '@/hooks/useMetrics';
import { useFocusTrap } from '@/hooks/useFocusTrap';
import type { TrendPoint, WireMetricsDashboard } from '@selva/shared-types';
import { formatDuration, formatHM } from '@/lib/format-time';

interface MetricsDashboardProps {
  open: boolean;
  onClose: () => void;
}

const PERIODS: MetricsPeriod[] = ['1h', '6h', '24h', '7d', '30d'];

const LABEL = 'pixel-text text-[8px] uppercase text-slate-300';
const SMALL = 'font-mono text-[10px] text-slate-300';

/**
 * Inline SVG sparkline from an array of TrendPoints.
 * Zero-dependency alternative to chart libraries. Strokes with
 * `currentColor`, so the caller sets the colour with a text class.
 */
const Sparkline: FC<{ data: TrendPoint[]; className: string }> = ({ data, className }) => {
  if (!data || data.length < 2) {
    return <p className={SMALL}>Not enough data yet</p>;
  }

  const values = data.map((d) => d.value);
  const max = Math.max(...values, 1);
  const min = Math.min(...values);
  const range = max - min || 1;
  const w = 120;
  const h = 24;

  const points = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * w;
      const y = h - ((v - min) / range) * (h - 4) - 2;
      return `${x},${y}`;
    })
    .join(' ');

  return (
    <svg width={w} height={h} className={`inline-block ${className}`} aria-hidden="true">
      <polyline
        points={points}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
};

const StatCard: FC<{
  label: string;
  value: string;
  subtext?: string;
  valueClass?: string;
}> = ({ label, value, subtext, valueClass = 'text-white' }) => (
  <div className="retro-panel px-3 py-2 animate-fade-in-up">
    <p className={LABEL}>{label}</p>
    <p className={`font-mono text-lg font-bold tabular-nums ${valueClass}`}>{value}</p>
    {subtext && <p className={SMALL}>{subtext}</p>}
  </div>
);

function errorRateCard(rate: number | null): { value: string; subtext?: string; valueClass?: string } {
  if (rate === null || rate === undefined) {
    return { value: '—', subtext: 'no task events in period' };
  }
  const value = `${rate.toFixed(1)}%`;
  if (rate > 10) return { value, subtext: 'above 10%', valueClass: 'text-red-400 [[data-theme=day]_&]:text-red-700' };
  if (rate > 5) return { value, subtext: 'above 5%', valueClass: 'text-amber-400 [[data-theme=day]_&]:text-amber-800' };
  return { value };
}

/**
 * Inference token volume per provider and model. Never spend: the ledger
 * does not yet record whether a call was paid from a provider credit grant
 * or in cash, so no money figure is shown here.
 */
const TokenUsage: FC<{ rows: WireMetricsDashboard['cost_breakdown'] }> = ({ rows }) => {
  const maxTokens = Math.max(...rows.map((r) => r.total_tokens), 1);
  return (
    <section className="retro-panel px-3 py-2" aria-labelledby="metrics-tokens-title">
      <h3 id="metrics-tokens-title" className={`${LABEL} mb-1`}>
        Inference tokens by provider
      </h3>
      <p className={`${SMALL} mb-2`}>Token volume, not spend.</p>
      {rows.length === 0 ? (
        <p className={SMALL}>No inference calls in this period.</p>
      ) : (
        <ul className="space-y-1.5">
          {rows.map((row) => {
            const name = `${row.provider} · ${row.model}`;
            const pct = (row.total_tokens / maxTokens) * 100;
            return (
              <li
                key={`${row.provider}/${row.model}`}
                className="grid grid-cols-[1fr_auto] items-center gap-x-2 gap-y-0.5 sm:grid-cols-[minmax(0,14rem)_1fr_auto]"
              >
                <span className={`col-span-2 truncate sm:col-span-1 ${SMALL}`} title={name}>
                  {name}
                </span>
                <div className="h-2 rounded-full bg-slate-700" aria-hidden="true">
                  <div
                    className="h-full rounded-full bg-indigo-500 transition-[width] duration-500 ease-out motion-reduce:transition-none"
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <span className="text-right font-mono text-[10px] tabular-nums text-white">
                  {row.total_tokens.toLocaleString()} tok · {row.call_count.toLocaleString()}{' '}
                  {row.call_count === 1 ? 'call' : 'calls'}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
};

export const MetricsDashboard: FC<MetricsDashboardProps> = ({
  open,
  onClose,
}) => {
  const { dashboard, loading, error, lastUpdated, period, setPeriod, refresh } = useMetrics(open);
  const trapRef = useFocusTrap<HTMLDivElement>(open);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  const statusLine = loading
    ? 'Updating…'
    : lastUpdated
      ? `Updated ${formatHM(lastUpdated)}`
      : '';

  return (
    <div
      className="fixed inset-0 z-modal flex items-center justify-center p-2 sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="metrics-dashboard-title"
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 animate-fade-in"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Modal */}
      <div
        ref={trapRef}
        className="relative z-10 w-full max-w-2xl max-h-[85vh] overflow-y-auto bg-slate-900 pixel-border-accent p-4 animate-pop-in"
      >
        {/* Header */}
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2
              id="metrics-dashboard-title"
              className="pixel-text text-sm uppercase tracking-wider text-amber-400 [[data-theme=day]_&]:text-amber-800"
            >
              Ops Metrics
            </h2>
            <p role="status" className={`${SMALL} mt-1 min-h-[1em]`}>
              {statusLine}
            </p>
          </div>
          <div className="flex items-center gap-3">
            {/* Period selector */}
            <div className="flex gap-1" role="group" aria-label="Period">
              {PERIODS.map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => setPeriod(p)}
                  aria-pressed={period === p}
                  className={`min-h-[44px] px-2.5 font-mono text-xs uppercase md:min-h-0 md:px-2 md:py-1 md:text-[10px] ${
                    period === p
                      ? 'bg-amber-400 text-black'
                      : 'bg-slate-800 text-slate-300 hover:text-white'
                  }`}
                >
                  {p}
                </button>
              ))}
            </div>
            <CloseButton onClick={onClose} label="Close metrics dashboard" shortcut="ESC" />
          </div>
        </div>

        {error && (
          <div
            role="alert"
            className="retro-panel mb-4 flex flex-wrap items-center justify-between gap-2 px-3 py-2"
          >
            <p className="font-mono text-[10px] text-white">
              Couldn&apos;t load metrics. {error}
              {dashboard && lastUpdated ? ` Showing data from ${formatHM(lastUpdated)}.` : ''}
            </p>
            <button
              type="button"
              onClick={refresh}
              className="min-h-[44px] bg-slate-800 px-3 font-mono text-xs uppercase text-white hover:bg-slate-700 md:min-h-0 md:py-1 md:text-[10px]"
            >
              Retry
            </button>
          </div>
        )}

        {loading && !dashboard ? (
          <p className="py-12 text-center font-mono text-[10px] text-slate-300">Loading metrics…</p>
        ) : dashboard ? (
          <div className="space-y-4">
            {/* Stat cards grid */}
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <StatCard
                label="Utilization"
                value={`${dashboard.agent_utilization_pct.toFixed(1)}%`}
              />
              <StatCard
                label="Tasks created"
                value={String(dashboard.task_throughput.total)}
                subtext={
                  dashboard.task_throughput.avg_duration_s
                    ? `avg ${formatDuration(dashboard.task_throughput.avg_duration_s)} to finish`
                    : undefined
                }
              />
              <StatCard
                label="Approval Queue"
                value={String(dashboard.approval_latency.pending_count)}
                subtext={
                  dashboard.approval_latency.avg_seconds
                    ? `pending now · avg ${formatDuration(dashboard.approval_latency.avg_seconds)} to answer`
                    : 'pending now'
                }
              />
              <StatCard label="Error Rate" {...errorRateCard(dashboard.error_rate)} />
            </div>

            {/* Sparklines */}
            <div className="grid grid-cols-2 gap-2">
              <div className="retro-panel px-3 py-2">
                <p className={`${LABEL} mb-1`}>Task Volume</p>
                <Sparkline data={dashboard.trends.tasks ?? []} className="text-indigo-400" />
              </div>
              <div className="retro-panel px-3 py-2">
                <p className={`${LABEL} mb-1`}>Errors</p>
                <Sparkline data={dashboard.trends.errors ?? []} className="text-red-400 [[data-theme=day]_&]:text-red-700" />
              </div>
            </div>

            <TokenUsage rows={dashboard.cost_breakdown} />

            {/* Task status breakdown */}
            <div className="retro-panel px-3 py-2">
              <p className={`${LABEL} mb-2`}>Task Status</p>
              {Object.keys(dashboard.task_throughput.status_counts).length === 0 ? (
                <p className={SMALL}>No tasks created in this period.</p>
              ) : (
                <div className="flex flex-wrap gap-x-3 gap-y-1 font-mono text-[10px]">
                  {Object.entries(dashboard.task_throughput.status_counts).map(
                    ([status, count]) => (
                      <span key={status} className="text-slate-300">
                        <span
                          className={`tabular-nums ${
                            status === 'completed'
                              ? 'text-emerald-400 [[data-theme=day]_&]:text-emerald-800'
                              : status === 'failed'
                                ? 'text-red-400 [[data-theme=day]_&]:text-red-700'
                                : status === 'running'
                                  ? 'text-blue-400 [[data-theme=day]_&]:text-blue-700'
                                  : 'text-white'
                          }`}
                        >
                          {count}
                        </span>{' '}
                        {status}
                      </span>
                    ),
                  )}
                </div>
              )}
            </div>

            {/* Recent errors */}
            {dashboard.recent_errors.length > 0 && (
              <div className="retro-panel px-3 py-2">
                <p className={`${LABEL} mb-2`}>Recent Errors</p>
                <ul className="max-h-32 space-y-1 overflow-y-auto">
                  {dashboard.recent_errors.map((err) => (
                    <li key={err.id} className="bg-slate-800/40 px-2 py-1 font-mono text-[10px]">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-red-400 [[data-theme=day]_&]:text-red-700">{err.event_type}</span>
                        <span className="text-slate-300">
                          {err.created_at ? formatHM(err.created_at) : ''}
                        </span>
                      </div>
                      {err.error_message && (
                        <p className="truncate text-slate-300" title={err.error_message}>
                          {err.error_message}
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ) : error ? null : (
          <p className="py-12 text-center font-mono text-[10px] text-slate-300">
            No metrics data available
          </p>
        )}
      </div>
    </div>
  );
};
