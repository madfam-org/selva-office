import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { useCalendar } from '../../hooks/useCalendar';

describe('useCalendar', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('starts with default state', () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ connected: false }),
    });
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useCalendar());

    expect(result.current.events).toEqual([]);
    expect(result.current.isBusy).toBe(false);
    expect(result.current.connected).toBe(false);
    expect(result.current.status).toBe('idle');
    expect(result.current.error).toBeNull();
  });

  it('connect() transitions to connected on success', async () => {
    const fetchMock = vi.fn()
      // First call: fetchStatus on mount
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ connected: false }),
      })
      // Second call: connect POST
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ connected: true, provider: 'google' }),
      })
      // Third call: fetchEvents after connect
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ events: [], is_busy: false }),
      });
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useCalendar());

    // Wait for mount effect
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    await act(async () => {
      const ok = await result.current.connect('google', 'test-token', 'refresh-token');
      expect(ok).toBe(true);
    });

    expect(result.current.connected).toBe(true);
    expect(result.current.status).toBe('connected');
  });

  it('connect() transitions to error on failure', async () => {
    const fetchMock = vi.fn()
      // fetchStatus on mount
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ connected: false }),
      })
      // connect POST failure
      .mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: async () => ({ detail: 'Invalid token' }),
      });
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useCalendar());

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    await act(async () => {
      const ok = await result.current.connect('google', 'bad-token');
      expect(ok).toBe(false);
    });

    expect(result.current.status).toBe('error');
    expect(result.current.error).toBe('Invalid token');
  });

  it('disconnect() clears state', async () => {
    const fetchMock = vi.fn()
      // fetchStatus on mount — connected
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ connected: true, provider: 'google' }),
      })
      // fetchEvents (after connected state detected)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          events: [{ id: 'e1', title: 'Test', start: '2026-03-14T10:00:00Z', end: '2026-03-14T11:00:00Z', is_all_day: false, meeting_url: null, organizer: '', attendees: [], provider: 'google' }],
          is_busy: false,
        }),
      })
      // disconnect DELETE
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ disconnected: true }),
      });
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useCalendar());

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    // Wait for events fetch triggered by connected state
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    await act(async () => {
      const ok = await result.current.disconnect();
      expect(ok).toBe(true);
    });

    expect(result.current.connected).toBe(false);
    expect(result.current.events).toEqual([]);
    expect(result.current.isBusy).toBe(false);
    expect(result.current.status).toBe('idle');
  });

  it('connect() handles network error', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ connected: false }),
      })
      .mockRejectedValueOnce(new Error('Network down'));
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useCalendar());

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    await act(async () => {
      const ok = await result.current.connect('google', 'token');
      expect(ok).toBe(false);
    });

    expect(result.current.status).toBe('error');
    expect(result.current.error).toBe('Network error — could not reach server');
  });

  it('fires onBusyChange callback when busy state changes', async () => {
    const onBusyChange = vi.fn();
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ connected: true, provider: 'google' }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          events: [{ id: 'e1', title: 'Meeting', start: '2026-03-14T10:00:00Z', end: '2026-03-14T11:00:00Z', is_all_day: false, meeting_url: null, organizer: '', attendees: [], provider: 'google' }],
          is_busy: true,
        }),
      });
    vi.stubGlobal('fetch', fetchMock);

    renderHook(() => useCalendar({ onBusyChange }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    // Wait for the events fetch triggered by connected effect
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(onBusyChange).toHaveBeenCalledWith(true);
  });
});
