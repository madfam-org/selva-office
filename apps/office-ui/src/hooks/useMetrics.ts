'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import type { WireMetricsDashboard } from '@selva/shared-types';
import { apiFetch } from '@/lib/api';

const POLL_INTERVAL_MS = 30000;

export type MetricsPeriod = '1h' | '6h' | '24h' | '7d' | '30d';

interface MetricsState {
  // Wire shape from /api/v1/metrics/dashboard. The raw generated type
  // exposes `task_throughput` / `approval_latency` / `cost_breakdown` /
  // `recent_errors` as loose `dict[str, Any]` (FastAPI returns plain
  // dicts on the Python side); WireMetricsDashboard intersects those
  // with narrowed sub-shapes. See generated/helpers.ts for the contract.
  dashboard: WireMetricsDashboard | null;
  loading: boolean;
  /** Why the last read failed; null after a successful read. */
  error: string | null;
  /** When `dashboard` was last read successfully. */
  lastUpdated: Date | null;
  period: MetricsPeriod;
  setPeriod: (p: MetricsPeriod) => void;
  refresh: () => void;
}

/**
 * React hook for the ops metrics dashboard.
 * Polls /api/v1/metrics/dashboard every 30s while `enabled` (the modal is
 * open). Changing the period triggers an immediate refresh. A failed read
 * keeps the last good data and reports the failure; it is never shown as
 * "no data".
 */
export function useMetrics(enabled = true): MetricsState {
  const [dashboard, setDashboard] = useState<WireMetricsDashboard | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [period, setPeriodState] = useState<MetricsPeriod>('24h');
  const pollRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined);

  const fetchDashboard = useCallback(async (p: MetricsPeriod) => {
    try {
      setLoading(true);
      const res = await apiFetch(`/api/v1/metrics/dashboard?period=${p}`);
      if (!res.ok) {
        setError(`The metrics service answered ${res.status}.`);
        return;
      }
      const data = (await res.json()) as WireMetricsDashboard;
      setDashboard(data);
      setError(null);
      setLastUpdated(new Date());
    } catch {
      setError('The metrics service could not be reached.');
    } finally {
      setLoading(false);
    }
  }, []);

  const setPeriod = useCallback((p: MetricsPeriod) => {
    setPeriodState(p);
  }, []);

  const refresh = useCallback(() => {
    void fetchDashboard(period);
  }, [fetchDashboard, period]);

  useEffect(() => {
    if (!enabled) return;
    void fetchDashboard(period);
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(() => void fetchDashboard(period), POLL_INTERVAL_MS);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [enabled, period, fetchDashboard]);

  return { dashboard, loading, error, lastUpdated, period, setPeriod, refresh };
}
