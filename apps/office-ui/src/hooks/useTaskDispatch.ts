'use client';

import { useState, useCallback } from 'react';
import { apiFetch } from '@/lib/api';

export interface DispatchRequest {
  description: string;
  graph_type: 'coding' | 'research' | 'crm' | 'deployment' | 'sequential' | 'parallel' | 'custom' | 'meeting';
  assigned_agent_ids?: string[];
  required_skills?: string[];
  payload?: Record<string, unknown>;
  workflow_id?: string;
}

export interface DispatchResponse {
  id: string;
  description: string;
  graph_type: string;
  status: string;
  assigned_agent_ids: string[];
  created_at: string;
}

export type DispatchStatus = 'idle' | 'submitting' | 'success' | 'error';

export function useTaskDispatch(): {
  dispatch: (request: DispatchRequest) => Promise<DispatchResponse | null>;
  status: DispatchStatus;
  error: string | null;
  lastDispatchedTask: DispatchResponse | null;
  reset: () => void;
} {
  const [status, setStatus] = useState<DispatchStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  const [lastDispatchedTask, setLastDispatchedTask] = useState<DispatchResponse | null>(null);

  const dispatch = useCallback(async (request: DispatchRequest): Promise<DispatchResponse | null> => {
    setStatus('submitting');
    setError(null);

    try {
      const res = await apiFetch('/api/v1/swarms/dispatch', {
        method: 'POST',
        body: JSON.stringify(request),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        const detail = (body as Record<string, unknown>).detail;
        setError(typeof detail === 'string' ? detail : `Request failed (${res.status})`);
        setStatus('error');
        return null;
      }

      const data = (await res.json()) as DispatchResponse;
      setLastDispatchedTask(data);
      setStatus('success');
      return data;
    } catch {
      setError('Network error — could not reach server');
      setStatus('error');
      return null;
    }
  }, []);

  const reset = useCallback(() => {
    setStatus('idle');
    setError(null);
    setLastDispatchedTask(null);
  }, []);

  return { dispatch, status, error, lastDispatchedTask, reset };
}
