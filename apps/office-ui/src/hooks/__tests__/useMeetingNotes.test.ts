import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { useMeetingNotes } from '../../hooks/useMeetingNotes';

describe('useMeetingNotes', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('starts with idle status and null notes', () => {
    const { result } = renderHook(() => useMeetingNotes());

    expect(result.current.status).toBe('idle');
    expect(result.current.notes).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it('transitions to dispatching then processing on dispatch', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ id: 'task-meeting-1', status: 'queued' }),
    });
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useMeetingNotes());

    await act(async () => {
      void result.current.dispatchMeetingNotes('blob:recording-url');
    });

    // After dispatch completes, status should be 'processing'
    expect(result.current.status).toBe('processing');
  });

  it('sets error on dispatch failure', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({ detail: 'Server error' }),
    });
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useMeetingNotes());

    await act(async () => {
      await result.current.dispatchMeetingNotes('blob:recording-url');
    });

    expect(result.current.status).toBe('error');
    expect(result.current.error).toBe('Server error');
  });

  it('sets error on network failure', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error('Network down'));
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useMeetingNotes());

    await act(async () => {
      await result.current.dispatchMeetingNotes('blob:recording-url');
    });

    expect(result.current.status).toBe('error');
    expect(result.current.error).toBe('Network error — could not dispatch meeting notes task');
  });

  it('reset() clears to idle state', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ id: 'task-meeting-2', status: 'queued' }),
    });
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useMeetingNotes());

    await act(async () => {
      void result.current.dispatchMeetingNotes('blob:recording-url');
    });

    act(() => {
      result.current.reset();
    });

    expect(result.current.status).toBe('idle');
    expect(result.current.notes).toBeNull();
    expect(result.current.error).toBeNull();
  });
});
