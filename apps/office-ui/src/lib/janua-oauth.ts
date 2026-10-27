/**
 * Server-side helpers for the Janua OAuth 2.0 authorization-code + PKCE flow.
 *
 * Flow:
 *   1. GET /api/auth/login: generates `state` and the PKCE verifier, stores
 *      them with the post-login redirect in one short-lived httpOnly cookie
 *      (OAUTH_FLOW_COOKIE), and redirects to Janua's authorize endpoint.
 *   2. GET /api/auth/callback/janua: requires the `state` query parameter to
 *      equal the stored value (constant-time), deletes the cookie, and only
 *      then exchanges the code using the stored verifier.
 *
 * Mirrors the admin app's server-side SSO route (apps/admin/src/app/api/auth/sso).
 */

import { januaClientId, januaIssuer } from './verify-session';

/**
 * `__Host-` prefix: the browser only accepts it with Secure, Path=/ and no
 * Domain attribute, so a sibling subdomain cannot plant or overwrite it.
 */
export const OAUTH_FLOW_COOKIE = '__Host-selva-oauth';

/** Lifetime of the flow cookie (10 minutes covers slow sign-ins and MFA). */
export const OAUTH_FLOW_MAX_AGE_S = 600;

export const DEFAULT_POST_LOGIN_PATH = '/office';

export const CALLBACK_PATH = '/api/auth/callback/janua';

export interface OAuthFlowState {
  state: string;
  verifier: string;
  redirect: string;
}

export function januaIssuerUrl(): string {
  return januaIssuer().replace(/\/+$/, '');
}

export { januaClientId };

/** Public origin of this app, honouring the tunnel/proxy forwarding headers. */
export function getOrigin(request: Request): string {
  const h = request.headers;
  const host = h.get('x-forwarded-host') || h.get('host') || new URL(request.url).host;
  const proto = h.get('x-forwarded-proto') || 'https';
  return `${proto}://${host}`;
}

function base64UrlEncode(bytes: Uint8Array): string {
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function base64UrlDecode(value: string): Uint8Array {
  const base64 = value.replace(/-/g, '+').replace(/_/g, '/');
  const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4);
  const binary = atob(padded);
  return Uint8Array.from(binary, (c) => c.charCodeAt(0));
}

/** Cryptographically random base64url string (default 32 bytes = 256 bits). */
export function randomToken(byteLength = 32): string {
  const bytes = new Uint8Array(byteLength);
  crypto.getRandomValues(bytes);
  return base64UrlEncode(bytes);
}

/** RFC 7636 S256 code challenge. */
export async function pkceChallenge(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier));
  return base64UrlEncode(new Uint8Array(digest));
}

/**
 * Compare two strings without short-circuiting on the first differing byte.
 * Unequal lengths return false immediately (state values have a fixed length).
 */
export function constantTimeEqual(a: string, b: string): boolean {
  const left = new TextEncoder().encode(a);
  const right = new TextEncoder().encode(b);
  if (left.length !== right.length) return false;
  let diff = 0;
  for (let i = 0; i < left.length; i += 1) diff |= left[i] ^ right[i];
  return diff === 0;
}

/**
 * Normalise a post-login redirect target to a same-origin relative path.
 * Absolute URLs, scheme-relative `//host`, backslashes and control characters
 * fall back to `fallback`.
 */
export function safeRedirectPath(
  value: string | null | undefined,
  fallback = DEFAULT_POST_LOGIN_PATH,
): string {
  if (!value || !value.startsWith('/') || value.startsWith('//')) return fallback;
  // eslint-disable-next-line no-control-regex
  if (/[\\\u0000-\u001f\u007f]/.test(value)) return fallback;
  try {
    const base = 'http://redirect.invalid';
    const parsed = new URL(value, base);
    if (parsed.origin !== base) return fallback;
    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch {
    return fallback;
  }
}

export function encodeFlowState(flow: OAuthFlowState): string {
  return base64UrlEncode(new TextEncoder().encode(JSON.stringify(flow)));
}

/** Parse the flow cookie; returns null for anything malformed. */
export function decodeFlowState(value: string | null | undefined): OAuthFlowState | null {
  if (!value) return null;
  try {
    const parsed: unknown = JSON.parse(new TextDecoder().decode(base64UrlDecode(value)));
    if (!parsed || typeof parsed !== 'object') return null;
    const { state, verifier, redirect } = parsed as Record<string, unknown>;
    if (typeof state !== 'string' || state.length < 22) return null;
    if (typeof verifier !== 'string' || verifier.length < 43) return null;
    if (typeof redirect !== 'string') return null;
    return { state, verifier, redirect };
  } catch {
    return null;
  }
}

export function flowCookieOptions(maxAge = OAUTH_FLOW_MAX_AGE_S) {
  return {
    httpOnly: true,
    secure: true,
    sameSite: 'lax' as const,
    path: '/',
    maxAge,
  };
}
