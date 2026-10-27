/**
 * Session verification for office-ui, shared by the edge middleware, server
 * components (e.g. /bundles) and route handlers.
 *
 * The `janua-session` cookie holds a Janua-issued access token: the OIDC token
 * stored by /api/auth/callback/janua, or a guest token from Janua's
 * /api/v1/auth/guest (set by /guest). office-ui does not mint its own session.
 *
 * Checks, mirroring nexus-api `verify_jwt`:
 *   - signature against Janua's JWKS, RS256 only
 *   - `iss` = Janua issuer, `exp` required, 30 s clock tolerance
 *   - `aud` contains the office-ui OAuth client id
 *
 * Janua guest tokens carry Janua's platform audience rather than a client id,
 * so a token that fails the audience check is still accepted as a *guest*
 * session when its verified claims are exactly a guest grant
 * (`type: "guest_access"`, `roles: ["guest"]`). Guests get no other role.
 *
 * Never throws: every failure maps to `unauthenticated`.
 * Edge-runtime compatible: `jose` + Web Crypto only.
 */

import { createRemoteJWKSet, jwtVerify, type JWTPayload, type JWTVerifyGetKey } from 'jose';

const DEFAULT_JANUA_URL = 'https://auth.madfam.io';
const JANUA_ALGORITHMS = ['RS256'];
const CLOCK_TOLERANCE_S = 30;

export const SESSION_COOKIE = 'janua-session';

export type SessionKind = 'user' | 'guest';

export type SessionCheck =
  | { status: 'ok'; kind: SessionKind; claims: JWTPayload; roles: string[] }
  | { status: 'unauthenticated' };

export function januaIssuer(): string {
  return (
    process.env.NEXT_PUBLIC_JANUA_ISSUER_URL || process.env.JANUA_ISSUER_URL || DEFAULT_JANUA_URL
  );
}

export function januaJwksUrl(): string {
  return `${januaIssuer().replace(/\/+$/, '')}/.well-known/jwks.json`;
}

/** Same precedence as the login and callback routes (lib/janua-oauth.ts). */
export function januaClientId(): string {
  return process.env.NEXT_PUBLIC_JANUA_CLIENT_ID || process.env.JANUA_CLIENT_ID || 'selva-office';
}

const jwksByUrl = new Map<string, JWTVerifyGetKey>();

function remoteJwks(url: string): JWTVerifyGetKey {
  let jwks = jwksByUrl.get(url);
  if (!jwks) {
    jwks = createRemoteJWKSet(new URL(url));
    jwksByUrl.set(url, jwks);
  }
  return jwks;
}

/** Roles from `roles` or `role`, as an array or a comma-separated string. */
export function extractRoles(claims: JWTPayload): string[] {
  const raw = claims.roles ?? claims.role;
  if (Array.isArray(raw)) {
    return raw.filter((r): r is string => typeof r === 'string').map((r) => r.trim());
  }
  if (typeof raw === 'string') {
    return raw
      .split(',')
      .map((r) => r.trim())
      .filter(Boolean);
  }
  return [];
}

function audienceIncludes(claims: JWTPayload, audience: string): boolean {
  const aud = claims.aud;
  return Array.isArray(aud) ? aud.includes(audience) : aud === audience;
}

function isGuestGrant(claims: JWTPayload, roles: string[]): boolean {
  return claims.type === 'guest_access' && roles.length === 1 && roles[0] === 'guest';
}

/**
 * Local-development escape hatch, matching the login page's dev button and
 * nexus-api's DEV_AUTH_BYPASS. `NODE_ENV` is inlined as "production" by
 * `next build`, so this is never true in a deployed build.
 */
function devAuthBypassEnabled(): boolean {
  if (process.env.NODE_ENV !== 'development') return false;
  return (
    process.env.DEV_AUTH_BYPASS === 'true' ||
    process.env.NEXT_PUBLIC_DEV_AUTH_BYPASS === 'true' ||
    !process.env.NEXT_PUBLIC_JANUA_ISSUER_URL
  );
}

export async function verifySessionToken(token: string | null | undefined): Promise<SessionCheck> {
  if (!token) return { status: 'unauthenticated' };

  if (devAuthBypassEnabled()) {
    return { status: 'ok', kind: 'user', claims: { sub: 'dev-user', roles: ['admin'], is_admin: true }, roles: ['admin'] };
  }

  let claims: JWTPayload;
  try {
    // Audience is checked below so the guest-token case can be told apart;
    // signature, algorithm, issuer and expiry are enforced here.
    const verified = await jwtVerify(token, remoteJwks(januaJwksUrl()), {
      algorithms: JANUA_ALGORITHMS,
      issuer: januaIssuer(),
      requiredClaims: ['exp'],
      clockTolerance: CLOCK_TOLERANCE_S,
    });
    claims = verified.payload;
  } catch {
    return { status: 'unauthenticated' };
  }

  const roles = extractRoles(claims);
  if (audienceIncludes(claims, januaClientId())) {
    return { status: 'ok', kind: 'user', claims, roles };
  }
  if (isGuestGrant(claims, roles)) {
    return { status: 'ok', kind: 'guest', claims, roles: ['guest'] };
  }
  return { status: 'unauthenticated' };
}
