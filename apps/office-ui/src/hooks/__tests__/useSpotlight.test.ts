import { describe, it, expect, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useSpotlight } from '../useSpotlight';

describe('useSpotlight', () => {
  it('initializes with inactive state', () => {
    const { result } = renderHook(() =>
      useSpotlight({
        localSessionId: 'local-1',
        sendSpotlightStart: vi.fn(),
        sendSpotlightStop: vi.fn(),
        enabled: true,
      }),
    );

    expect(result.current.active).toBe(false);
    expect(result.current.isPresenting).toBe(false);
    expect(result.current.presenterName).toBeNull();
    expect(result.current.presenterSessionId).toBeNull();
  });

  it('handles start and stop cycle via handleSpotlightActive', () => {
    const sendStart = vi.fn();
    const sendStop = vi.fn();

    const { result } = renderHook(() =>
      useSpotlight({
        localSessionId: 'local-1',
        sendSpotlightStart: sendStart,
        sendSpotlightStop: sendStop,
        enabled: true,
      }),
    );

    // Simulate receiving a spotlight_active event (someone started presenting)
    act(() => {
      result.current.handleSpotlightActive({
        sessionId: 'local-1',
        name: 'Alice',
        active: true,
      });
    });

    expect(result.current.active).toBe(true);
    expect(result.current.isPresenting).toBe(true);
    expect(result.current.presenterName).toBe('Alice');
    expect(result.current.presenterSessionId).toBe('local-1');

    // Simulate stop
    act(() => {
      result.current.handleSpotlightActive({
        sessionId: 'local-1',
        active: false,
      });
    });

    expect(result.current.active).toBe(false);
    expect(result.current.isPresenting).toBe(false);
    expect(result.current.presenterName).toBeNull();
    expect(result.current.presenterSessionId).toBeNull();
  });

  it('sends spotlight_start when startSpotlight is called', () => {
    const sendStart = vi.fn();

    const { result } = renderHook(() =>
      useSpotlight({
        localSessionId: 'local-1',
        sendSpotlightStart: sendStart,
        sendSpotlightStop: vi.fn(),
        enabled: true,
      }),
    );

    act(() => {
      result.current.startSpotlight();
    });

    expect(sendStart).toHaveBeenCalledOnce();
  });

  it('sends spotlight_stop when stopSpotlight is called', () => {
    const sendStop = vi.fn();

    const { result } = renderHook(() =>
      useSpotlight({
        localSessionId: 'local-1',
        sendSpotlightStart: vi.fn(),
        sendSpotlightStop: sendStop,
        enabled: true,
      }),
    );

    act(() => {
      result.current.stopSpotlight();
    });

    expect(sendStop).toHaveBeenCalledOnce();
  });

  it('does not send when disabled', () => {
    const sendStart = vi.fn();
    const sendStop = vi.fn();

    const { result } = renderHook(() =>
      useSpotlight({
        localSessionId: 'local-1',
        sendSpotlightStart: sendStart,
        sendSpotlightStop: sendStop,
        enabled: false,
      }),
    );

    act(() => {
      result.current.startSpotlight();
      result.current.stopSpotlight();
    });

    expect(sendStart).not.toHaveBeenCalled();
    expect(sendStop).not.toHaveBeenCalled();
  });

  it('identifies remote presenter as not presenting locally', () => {
    const { result } = renderHook(() =>
      useSpotlight({
        localSessionId: 'local-1',
        sendSpotlightStart: vi.fn(),
        sendSpotlightStop: vi.fn(),
        enabled: true,
      }),
    );

    act(() => {
      result.current.handleSpotlightActive({
        sessionId: 'remote-2',
        name: 'Bob',
        active: true,
      });
    });

    expect(result.current.active).toBe(true);
    expect(result.current.isPresenting).toBe(false);
    expect(result.current.presenterName).toBe('Bob');
    expect(result.current.presenterSessionId).toBe('remote-2');
  });
});
