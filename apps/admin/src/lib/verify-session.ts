/**
 * Admin session verification, shared by the edge middleware and any server
 * code that needs to know who is calling.
 *
 * The `janua-session` cookie holds one of two token kinds, depending on how
 * the callback route (api/auth/callback/route.ts) is configured:
 *
 *   - JANUA_SECRET_KEY / SESSION_SECRET set: an HS256 JWT minted by the
 *     callback with `iss: "selva-admin"`. Verified with that secret.
 *   - No secret: the Janua access token itself. Verified against Janua's JWKS
 *     (RS256 only), `iss` = Janua issuer, `aud` = the admin's OAuth client id,
 *     the same checks nexus-api applies in `verify_jwt`.
 *
 * Only the kind the current configuration issues is accepted. `exp` is
 * required in both cases. Any verification error yields `unauthenticated`;
 * a valid token without the `admin` role yields `forbidden`.
 *
 * Edge-runtime compatible: uses `jose` and Web Crypto only.
 */

import { createRemoteJWKSet, jwtVerify, type JWTPayload, type JWTVerifyGetKey } from 'jose';
import {
  ADMIN_SESSION_ISSUER,
  adminSessionSecret,
  januaClientId,
  januaIssuer,
  januaJwksUrl,
} from './janua-config';

export const ADMIN_ROLE = 'admin';

/** Janua signs access tokens with RS256 (see nexus-api `_JANUA_ALGORITHMS`). */
const JANUA_ALGORITHMS = ['RS256'];
const SESSION_ALGORITHMS = ['HS256'];

/** Clock-skew tolerance, matching nexus-api's `_JANUA_LEEWAY_SECONDS`. */
const CLOCK_TOLERANCE_S = 30;

export type AdminSessionCheck =
  | { status: 'ok'; claims: JWTPayload; roles: string[] }
  | { status: 'forbidden'; claims: JWTPayload; roles: string[] }
  | { status: 'unauthenticated' };

// Module-scope JWKS cache: createRemoteJWKSet keeps fetched keys in memory and
// refetches on an unknown `kid` (with its own cooldown).
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

async function verifyToken(token: string): Promise<JWTPayload> {
  const secret = adminSessionSecret();
  if (secret) {
    const { payload } = await jwtVerify(token, new TextEncoder().encode(secret), {
      algorithms: SESSION_ALGORITHMS,
      issuer: ADMIN_SESSION_ISSUER,
      requiredClaims: ['exp'],
      clockTolerance: CLOCK_TOLERANCE_S,
    });
    return payload;
  }

  const { payload } = await jwtVerify(token, remoteJwks(januaJwksUrl()), {
    algorithms: JANUA_ALGORITHMS,
    issuer: januaIssuer(),
    audience: januaClientId(),
    requiredClaims: ['exp'],
    clockTolerance: CLOCK_TOLERANCE_S,
  });
  return payload;
}

/**
 * Local-development escape hatch, mirroring nexus-api's
 * `environment == "development" and DEV_AUTH_BYPASS`. `NODE_ENV` is inlined
 * as "production" by `next build`, so this is never true in a deployed build.
 */
function devAuthBypassEnabled(): boolean {
  return process.env.NODE_ENV === 'development' && process.env.DEV_AUTH_BYPASS === 'true';
}

/**
 * Verify an admin session token and check for the admin role.
 * Never throws: every failure maps to `unauthenticated`.
 */
export async function checkAdminSession(
  token: string | null | undefined,
): Promise<AdminSessionCheck> {
  if (!token) return { status: 'unauthenticated' };

  if (devAuthBypassEnabled()) {
    return { status: 'ok', claims: { sub: 'dev-user' }, roles: [ADMIN_ROLE] };
  }

  let claims: JWTPayload;
  try {
    claims = await verifyToken(token);
  } catch {
    return { status: 'unauthenticated' };
  }

  const roles = extractRoles(claims);
  if (!roles.includes(ADMIN_ROLE)) {
    return { status: 'forbidden', claims, roles };
  }
  return { status: 'ok', claims, roles };
}
