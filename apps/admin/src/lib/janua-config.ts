/**
 * Janua (OIDC) configuration for the admin app.
 *
 * One place for the issuer, client id and session-signing secret so the SSO
 * initiation route, the callback route and the session verifier always agree
 * (the audience the verifier pins is the client id the SSO flow requests).
 *
 * Values are read on each call rather than at module load so runtime
 * environment variables are honoured and tests can stub them.
 */

const DEFAULT_JANUA_URL = 'https://auth.madfam.io';

/** Issuer of the admin's own session JWT (see api/auth/callback/route.ts). */
export const ADMIN_SESSION_ISSUER = 'selva-admin';

/** Cookie that carries the admin session token. */
export const ADMIN_SESSION_COOKIE = 'janua-session';

/** Base URL used to build the Janua authorize/token/userinfo endpoints. */
export function januaBaseUrl(): string {
  return (
    process.env.NEXT_PUBLIC_JANUA_BASE_URL ||
    process.env.NEXT_PUBLIC_JANUA_ISSUER_URL ||
    DEFAULT_JANUA_URL
  );
}

/** Expected `iss` claim of Janua-issued access tokens. */
export function januaIssuer(): string {
  return (
    process.env.NEXT_PUBLIC_JANUA_ISSUER_URL ||
    process.env.JANUA_ISSUER_URL ||
    DEFAULT_JANUA_URL
  );
}

/** Janua's public signing keys (same derivation as nexus-api `_fetch_jwks`). */
export function januaJwksUrl(): string {
  return `${januaIssuer().replace(/\/+$/, '')}/.well-known/jwks.json`;
}

/** OAuth client id; Janua access tokens carry it as the `aud` claim. */
export function januaClientId(): string {
  return (
    process.env.JANUA_CLIENT_ID ||
    process.env.NEXT_PUBLIC_JANUA_CLIENT_ID ||
    process.env.NEXT_PUBLIC_JANUA_PUBLISHABLE_KEY ||
    'selva-office'
  );
}

/**
 * HS256 secret for the admin session JWT. When empty, the callback stores the
 * Janua access token itself as the session and the verifier checks it against
 * Janua's JWKS instead.
 */
export function adminSessionSecret(): string {
  return process.env.JANUA_SECRET_KEY || process.env.SESSION_SECRET || '';
}

/**
 * Normalise a post-login redirect target to a same-origin relative path.
 * Anything else (absolute URLs, scheme-relative `//host`, backslashes,
 * control characters) falls back to `fallback`.
 */
export function safeRedirectPath(value: string | null | undefined, fallback = '/'): string {
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
