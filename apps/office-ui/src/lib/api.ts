/**
 * Authenticated API client for the Nexus API.
 *
 * Reads the `janua-session` cookie and passes it as a Bearer token.
 * All API calls go through this function so auth is handled once.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:4300';

function getSessionToken(): string | null {
  if (typeof document === 'undefined') return null;
  const match = document.cookie.match(/(?:^|;\s*)janua-session=([^;]*)/);
  return match?.[1] ?? null;
}

export async function apiFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const token = getSessionToken();
  const headers = new Headers(init?.headers);
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  headers.set('Content-Type', 'application/json');

  return fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    credentials: 'include',
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
    const payload = JSON.parse(atob(parts[1]));
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
