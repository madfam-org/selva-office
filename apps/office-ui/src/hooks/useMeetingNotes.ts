'use client';

import { useState, useCallback, useRef } from 'react';
import { apiFetch } from '@/lib/api';

export type MeetingNotesStatus = 'idle' | 'dispatching' | 'processing' | 'completed' | 'error';

export interface MeetingNotes {
  summary: string;
  action_items: Array<{ task: string; assignee: string; deadline: string }>;
  transcript: string;
}

interface DispatchResponse {
  id: string;
  status: string;
}

interface TaskResponse {
  id: string;
  status: string;
  payload?: {
    result?: MeetingNotes;
  };
}

const POLL_INTERVAL_MS = 3000;
const MAX_POLL_ATTEMPTS = 120; // 6 minutes max

export function useMeetingNotes(): {
  status: MeetingNotesStatus;
  notes: MeetingNotes | null;
  error: string | null;
  dispatchMeetingNotes: (recordingUrl: string) => Promise<void>;
  reset: () => void;
} {
  const [status, setStatus] = useState<MeetingNotesStatus>('idle');
  const [notes, setNotes] = useState<MeetingNotes | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortRef = useRef(false);

  const stopPolling = useCallback(() => {
    abortRef.current = true;
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const pollForResult = useCallback(async (taskId: string, attempt: number): Promise<void> => {
    if (abortRef.current || attempt >= MAX_POLL_ATTEMPTS) {
      if (attempt >= MAX_POLL_ATTEMPTS) {
        setError('Meeting notes generation timed out');
        setStatus('error');
      }
      return;
    }

    try {
      const res = await apiFetch(`/api/v1/swarms/tasks/${taskId}`);
      if (!res.ok) {
        setError('Failed to check task status');
        setStatus('error');
        return;
      }

      const task = (await res.json()) as TaskResponse;

      if (task.status === 'completed') {
        const result = task.payload?.result;
        if (result && typeof result === 'object' && 'summary' in result) {
          setNotes(result as MeetingNotes);
        } else {
          setNotes({
            summary: 'Meeting notes generated but no content available.',
            action_items: [],
            transcript: '',
          });
        }
        setStatus('completed');
        return;
      }

      if (task.status === 'failed') {
        setError('Meeting notes generation failed');
        setStatus('error');
        return;
      }

      // Still processing -- poll again
      pollTimerRef.current = setTimeout(() => {
        void pollForResult(taskId, attempt + 1);
      }, POLL_INTERVAL_MS);
    } catch {
      setError('Network error while checking task status');
      setStatus('error');
    }
  }, []);

  const dispatchMeetingNotes = useCallback(async (recordingUrl: string): Promise<void> => {
    stopPolling();
    abortRef.current = false;
    setStatus('dispatching');
    setError(null);
    setNotes(null);

    try {
      const res = await apiFetch('/api/v1/swarms/dispatch', {
        method: 'POST',
        body: JSON.stringify({
          description: 'Generate meeting notes from recording',
          graph_type: 'meeting',
          payload: { recording_url: recordingUrl },
        }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        const detail = (body as Record<string, unknown>).detail;
        setError(typeof detail === 'string' ? detail : `Dispatch failed (${res.status})`);
        setStatus('error');
        return;
      }

      const data = (await res.json()) as DispatchResponse;
      setStatus('processing');
      void pollForResult(data.id, 0);
    } catch {
      setError('Network error — could not dispatch meeting notes task');
      setStatus('error');
    }
  }, [stopPolling, pollForResult]);

  const reset = useCallback(() => {
    stopPolling();
    setStatus('idle');
    setNotes(null);
    setError(null);
  }, [stopPolling]);

  return { status, notes, error, dispatchMeetingNotes, reset };
}
