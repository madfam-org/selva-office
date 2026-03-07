'use client';

import { useState, useCallback } from 'react';

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:4300';

export interface DispatchRequest {
  description: string;
  graph_type: 'coding' | 'research' | 'crm' | 'sequential' | 'parallel';
  assigned_agent_ids?: string[];
  required_skills?: string[];
  payload?: Record<string, unknown>;
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
      const res = await fetch(`${API_BASE_URL}/api/v1/swarms/dispatch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
        credentials: 'include',
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
