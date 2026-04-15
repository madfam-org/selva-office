'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import type { ApprovalRequest, ApprovalResponse } from '@autoswarm/shared-types';
import { apiFetch, isDemo } from '@/lib/api';
import { MAX_RECONNECT_DELAY_MS } from '@/lib/constants';

const WS_URL =
  process.env.NEXT_PUBLIC_APPROVALS_WS_URL ?? 'ws://localhost:4300/api/v1/approvals/ws';

interface ApprovalsState {
  pendingApprovals: ApprovalRequest[];
  approve: (requestId: string, feedback?: string) => Promise<boolean>;
  deny: (requestId: string, feedback?: string) => Promise<boolean>;
  connected: boolean;
}

interface WSMessage {
  type: string;
  payload: unknown;
}

/**
 * React hook for the approval queue.
 * Connects to the nexus-api WebSocket, listens for approval_request events,
 * and provides approve/deny actions.
 */
export function useApprovals(): ApprovalsState {
  const demo = isDemo();
  const [pendingApprovals, setPendingApprovals] = useState<ApprovalRequest[]>([]);
  const [connected, setConnected] = useState(demo);
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
          const message: WSMessage = JSON.parse(event.data as string);

          switch (message.type) {
            case 'approval_request': {
              const request = message.payload as ApprovalRequest;
              setPendingApprovals((prev) => {
                // Avoid duplicates
                if (prev.some((a) => a.id === request.id)) return prev;
                return [...prev, request];
              });
              break;
            }

            case 'approval_resolved': {
              const response = message.payload as ApprovalResponse;
              setPendingApprovals((prev) =>
                prev.filter((a) => a.id !== response.requestId),
              );
              break;
            }

            case 'approval_batch': {
              const requests = message.payload as ApprovalRequest[];
              setPendingApprovals(requests);
              break;
            }

            case 'ping': {
              // Respond to keep-alive
              ws.send(JSON.stringify({ type: 'pong' }));
              break;
            }
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
          const delay = Math.min(MAX_RECONNECT_DELAY_MS, 1000 * Math.pow(2, reconnectAttempts.current)) + Math.random() * 1000;
          reconnectTimer.current = setTimeout(connect, delay);
        }
      };

      ws.onerror = () => {
        // onclose will fire after onerror, so reconnection is handled there
        setConnected(false);
      };
    } catch {
      setConnected(false);
      reconnectAttempts.current++;
      const delay = Math.min(MAX_RECONNECT_DELAY_MS, 1000 * Math.pow(2, reconnectAttempts.current)) + Math.random() * 1000;
      reconnectTimer.current = setTimeout(connect, delay);
    }
  }, []);

  useEffect(() => {
    if (demo) return; // Skip WebSocket in demo mode
    connect();

    return () => {
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current);
      }
      if (wsRef.current) {
        wsRef.current.close(1000, 'Component unmounted');
        wsRef.current = null;
      }
    };
  }, [connect]);

  const sendDecision = useCallback(
    async (requestId: string, decision: 'approve' | 'deny', feedback?: string): Promise<boolean> => {
      const body: Record<string, unknown> = {};
      if (feedback !== undefined) {
        body.feedback = feedback;
      }

      try {
        const res = await apiFetch(`/api/v1/approvals/${requestId}/${decision}`, {
          method: 'POST',
          body: JSON.stringify(body),
        });

        if (res.ok) {
          // Optimistically remove from pending -- the WS will also broadcast the
          // resolution, but removing immediately gives a snappy UI.
          setPendingApprovals((prev) => prev.filter((a) => a.id !== requestId));

          // PostHog analytics
          try {
            const { trackEvent } = await import('@/lib/analytics/posthog');
            trackEvent('selva_approval_responded', { action: decision, request_id: requestId });
          } catch {
            // analytics failure should not affect approval flow
          }

          return true;
        }
        return false;
      } catch {
        return false;
      }
    },
    [],
  );

  const approve = useCallback(
    async (requestId: string, feedback?: string): Promise<boolean> => {
      return sendDecision(requestId, 'approve', feedback);
    },
    [sendDecision],
  );

  const deny = useCallback(
    async (requestId: string, feedback?: string): Promise<boolean> => {
      return sendDecision(requestId, 'deny', feedback);
    },
    [sendDecision],
  );

  return {
    pendingApprovals,
    approve,
    deny,
    connected,
  };
}
