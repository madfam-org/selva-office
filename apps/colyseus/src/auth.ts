/**
 * JWT verification for Colyseus room authentication.
 *
 * Uses the `jose` library for JWKS-based verification.
 * Falls back to accepting any connection when DEV_AUTH_BYPASS is enabled.
 */

import { createRemoteJWKSet, jwtVerify, type JWTPayload } from "jose";
import { createLogger } from "@autoswarm/config/logging";

const logger = createLogger({ service: "colyseus" }).child({ component: "auth" });

const DEV_AUTH_BYPASS = process.env.DEV_AUTH_BYPASS === "true";
const JANUA_ISSUER_URL = process.env.JANUA_ISSUER_URL ?? "";

// Lazily-initialized JWKS function.
let jwks: ReturnType<typeof createRemoteJWKSet> | null = null;

function getJWKS(): ReturnType<typeof createRemoteJWKSet> {
  if (!jwks) {
    const jwksUrl = new URL("/.well-known/jwks.json", JANUA_ISSUER_URL);
    jwks = createRemoteJWKSet(jwksUrl);
  }
  return jwks;
}

export interface AuthResult {
  sub: string;
  orgId: string;
  roles: string[];
  name: string;
  isGuest: boolean;
}

/**
 * Verify a JWT token from the client's join options.
 *
 * In dev mode with DEV_AUTH_BYPASS=true, returns a synthetic auth result
 * allowing any connection.
 */
export async function verifyToken(
  token: string | undefined,
  options?: { name?: string },
): Promise<AuthResult> {
  if (DEV_AUTH_BYPASS) {
    return {
      sub: "dev-user-00000000",
      orgId: "dev-org",
      roles: ["admin", "tactician"],
      name: options?.name ?? "Player",
      isGuest: false,
    };
  }

  if (!token) {
    throw new Error("Missing authentication token");
  }

  try {
    const { payload } = await jwtVerify(token, getJWKS(), {
      issuer: JANUA_ISSUER_URL,
    });

    const roles = (payload as JWTPayload & { roles?: string[] }).roles ?? [];
    const orgId =
      (payload as JWTPayload & { org_id?: string; oid?: string }).org_id ??
      (payload as JWTPayload & { oid?: string }).oid ??
      "unknown";

    return {
      sub: payload.sub ?? "unknown",
      orgId,
      roles,
      name: (payload as JWTPayload & { name?: string }).name ?? options?.name ?? "Player",
      isGuest: roles.includes("guest"),
    };
  } catch (err) {
    logger.warn({ err }, "JWT verification failed");
    throw new Error("Invalid or expired token");
  }
}
