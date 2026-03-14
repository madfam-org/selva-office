import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { usePlayerStatus } from '../usePlayerStatus';

describe('usePlayerStatus', () => {
  let sendStatus: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    sendStatus = vi.fn();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('initializes with online status', () => {
    const { result } = renderHook(() =>
      usePlayerStatus({ sendStatus, enabled: true }),
    );
    expect(result.current.status).toBe('online');
  });

  it('changes status and sends to server', () => {
    const { result } = renderHook(() =>
      usePlayerStatus({ sendStatus, enabled: true }),
    );

    act(() => {
      result.current.changeStatus('busy');
    });

    expect(result.current.status).toBe('busy');
    expect(sendStatus).toHaveBeenCalledWith('busy');
  });

  it('does not send when disabled', () => {
    const { result } = renderHook(() =>
      usePlayerStatus({ sendStatus, enabled: false }),
    );

    act(() => {
      result.current.changeStatus('away');
    });

    expect(result.current.status).toBe('away');
    expect(sendStatus).not.toHaveBeenCalled();
  });

  it('accepts all valid status types', () => {
    const { result } = renderHook(() =>
      usePlayerStatus({ sendStatus, enabled: true }),
    );

    for (const status of ['online', 'away', 'busy', 'dnd'] as const) {
      act(() => {
        result.current.changeStatus(status);
      });
      expect(result.current.status).toBe(status);
    }
  });

  it('auto-away after 5 minutes of inactivity', () => {
    const { result } = renderHook(() =>
      usePlayerStatus({ sendStatus, enabled: true }),
    );

    expect(result.current.status).toBe('online');

    // Advance past the auto-away check interval (30s) and idle threshold (5min)
    act(() => {
      vi.advanceTimersByTime(5 * 60 * 1000 + 31_000);
    });

    expect(result.current.status).toBe('away');
    expect(sendStatus).toHaveBeenCalledWith('away');
  });
});
