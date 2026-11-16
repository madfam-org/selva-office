/**
 * MADFAM-internal (platform) admin predicates.
 *
 * Kept in a plain module, not the `'use client'` hook, so server components
 * and route handlers can call them too.
 *
 * Platform administration is read ONLY from Janua's `is_admin` claim, exactly
 * `true`. Role names in `role` / `roles` (organization membership roles) and
 * the email address are never read.
 */

/**
 * Pure predicate over a parsed-JWT-claims object: true IFF `claims.is_admin`
 * is exactly `true`.
 *
 * Default-deny invariant: any input shape we don't explicitly recognize
 * MUST return false. Unknown is not admin.
 */
export function isMadfamAdminClaims(claims: unknown): boolean {
  if (claims == null || typeof claims !== 'object') return false;
  return (claims as Record<string, unknown>).is_admin === true;
}

/**
 * Platform-operator gate for server-verified claims (same rule as
 * `isMadfamAdminClaims`).
 */
export function isPlatformAdminClaims(claims: unknown): boolean {
  return isMadfamAdminClaims(claims);
}
