import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

// Mock api module
vi.mock('@/lib/api', () => ({
  isDemo: vi.fn(() => false),
}));

import { useDemoMode } from '../useDemoMode';
import { isDemo } from '@/lib/api';

describe('useDemoMode', () => {
  let locationHref = '';

  beforeEach(() => {
    document.cookie = 'janua-session=; path=/; max-age=0';
    locationHref = '';
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: {
        ...window.location,
        get href() { return locationHref; },
        set href(v: string) { locationHref = v; },
      },
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('detects demo mode when isDemo returns true', () => {
    vi.mocked(isDemo).mockReturnValue(true);
    const { result } = renderHook(() => useDemoMode());
    expect(result.current.isDemo).toBe(true);
  });

  it('detects non-demo when isDemo returns false', () => {
    vi.mocked(isDemo).mockReturnValue(false);
    const { result } = renderHook(() => useDemoMode());
    expect(result.current.isDemo).toBe(false);
  });

  it('exitDemo clears cookie and navigates to /', () => {
    vi.mocked(isDemo).mockReturnValue(true);
    const { result } = renderHook(() => useDemoMode());

    act(() => {
      result.current.exitDemo();
    });

    expect(document.cookie).not.toContain('janua-session=');
    expect(locationHref).toBe('/');
  });

  it('convertToReal clears cookie and navigates to /login?redirect=/office', () => {
    vi.mocked(isDemo).mockReturnValue(true);
    const { result } = renderHook(() => useDemoMode());

    act(() => {
      result.current.convertToReal();
    });

    expect(document.cookie).not.toContain('janua-session=');
    expect(locationHref).toBe('/login?redirect=/office');
  });
});
