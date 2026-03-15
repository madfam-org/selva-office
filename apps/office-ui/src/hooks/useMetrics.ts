'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import type { MetricsDashboard } from '@autoswarm/shared-types';

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:4300';
const POLL_INTERVAL_MS = 30000;

export type MetricsPeriod = '1h' | '6h' | '24h' | '7d' | '30d';

interface MetricsState {
  dashboard: MetricsDashboard | null;
  loading: boolean;
  period: MetricsPeriod;
  setPeriod: (p: MetricsPeriod) => void;
}

/**
 * React hook for the ops metrics dashboard.
 * Polls /api/v1/metrics/dashboard every 30s.
 * Changing the period triggers an immediate refresh.
 */
export function useMetrics(): MetricsState {
  const [dashboard, setDashboard] = useState<MetricsDashboard | null>(null);
  const [loading, setLoading] = useState(false);
  const [period, setPeriodState] = useState<MetricsPeriod>('24h');
  const pollRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined);

  const fetchDashboard = useCallback(async (p: MetricsPeriod) => {
    try {
      setLoading(true);
      const res = await fetch(
        `${API_BASE_URL}/api/v1/metrics/dashboard?period=${p}`,
        { credentials: 'include' },
      );
      if (res.ok) {
        const data = (await res.json()) as MetricsDashboard;
        setDashboard(data);
      }
    } catch {
      // Silently fail
    } finally {
      setLoading(false);
    }
  }, []);

  const setPeriod = useCallback((p: MetricsPeriod) => {
    setPeriodState(p);
  }, []);

  useEffect(() => {
    void fetchDashboard(period);
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(() => void fetchDashboard(period), POLL_INTERVAL_MS);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [period, fetchDashboard]);

  return { dashboard, loading, period, setPeriod };
}
