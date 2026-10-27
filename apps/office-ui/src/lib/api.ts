/**
 * API client for the Nexus API.
 *
 * REST calls go to this app's same-origin proxy (`/api/nexus/<path>`, see
 * app/api/nexus/[...path]/route.ts), which verifies the session and attaches
 * the token from the `janua-session` cookie server-side. That cookie is
 * httpOnly for Janua sign-ins, so the token is never readable by browser JS.
 */

import { NEXUS_PROXY_PREFIX } from './nexus-proxy';

/**
 * The session token, when it is in a JS-readable cookie: the /guest and /demo
 * flows set it client-side. Returns null for httpOnly Janua sign-in sessions.
 * Used for the WebSocket and Colyseus handshakes, which cannot go through the
 * REST proxy.
 */
export function getSessionToken(): string | null {
  if (typeof document === 'undefined') return null;
  const match = document.cookie.match(/(?:^|;\s*)janua-session=([^;]*)/);
  return match?.[1] ?? null;
}

export async function apiFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const headers = new Headers(init?.headers);
  headers.set('Content-Type', 'application/json');

  return fetch(`${NEXUS_PROXY_PREFIX}${path}`, {
    ...init,
    headers,
    credentials: 'same-origin',
  });
}

/**
 * Parse the JWT session cookie to extract user claims.
 * Returns null if no valid cookie exists.
 */
export function getSessionUser(): { sub: string; email: string; name?: string; roles: string[] } | null {
  const token = getSessionToken();
  if (!token) return null;

  try {
    const parts = token.split('.');
    if (parts.length < 2) return null;
    // JWTs use base64url encoding (- instead of +, _ instead of /).
    // Restore standard base64 and pad to a multiple of 4.
    const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4);
    const payload = JSON.parse(atob(padded));
    return {
      sub: payload.sub ?? '',
      email: payload.email ?? '',
      name: payload.name,
      roles: payload.roles ?? [],
    };
  } catch {
    return null;
  }
}

/**
 * Check if the current session user has the admin role.
 */
export function isAdmin(): boolean {
  const user = getSessionUser();
  return user?.roles.includes('admin') ?? false;
}

/**
 * Check if the current session user is a guest.
 */
export function isGuest(): boolean {
  const user = getSessionUser();
  return user?.roles.includes('guest') ?? false;
}

/**
 * Check if the current session is a demo session.
 */
export function isDemo(): boolean {
  const user = getSessionUser();
  return user?.roles.includes('demo') ?? false;
}
