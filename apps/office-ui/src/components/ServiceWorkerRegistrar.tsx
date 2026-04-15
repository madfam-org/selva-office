'use client';

import { useEffect } from 'react';
import { registerServiceWorker } from '@/lib/register-sw';

/**
 * Client component that registers the service worker on mount.
 * Renders nothing — purely a side-effect component.
 */
export function ServiceWorkerRegistrar() {
  useEffect(() => {
    registerServiceWorker();
  }, []);

  return null;
}
