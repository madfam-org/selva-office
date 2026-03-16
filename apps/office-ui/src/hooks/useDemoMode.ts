'use client';

import { useCallback } from 'react';
import { isDemo } from '@/lib/api';

export function useDemoMode() {
  const demo = isDemo();

  const exitDemo = useCallback(() => {
    document.cookie = 'janua-session=; path=/; max-age=0';
    window.location.href = '/';
  }, []);

  const convertToReal = useCallback(() => {
    document.cookie = 'janua-session=; path=/; max-age=0';
    window.location.href = '/login?redirect=/office';
  }, []);

  return { isDemo: demo, exitDemo, convertToReal };
}
