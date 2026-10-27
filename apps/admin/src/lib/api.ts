/**
 * API client for the Nexus API (admin app).
 *
 * Requests go to this app's same-origin proxy (`/api/nexus/<path>`, see
 * app/api/nexus/[...path]/route.ts), which verifies the admin session and
 * attaches the Janua access token server-side from httpOnly cookies. The
 * token is never readable by browser JS.
 */

import { NEXUS_PROXY_PREFIX } from './nexus-proxy';

export async function apiFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const headers = new Headers(init?.headers);
  if (!headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  return fetch(`${NEXUS_PROXY_PREFIX}${path}`, {
    ...init,
    headers,
    credentials: 'same-origin',
  });
}
