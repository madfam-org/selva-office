/**
 * MADFAM-internal (platform) admin predicates.
 *
 * Kept in a plain module, not the `'use client'` hook, so server components
 * and route handlers can call them too.
 *
 * Janua's legacy `roles` claim mixes organization-membership roles
 * (`owner`/`admin`/`member` from ANY active org) with `admin` for Janua system
 * admins, so a bare `admin` string means "admin of some Janua org" and is not
 * a MADFAM platform role. These predicates do not read it.
 */

const ADMIN_EMAIL = 'admin@madfam.io';
const SUPERADMIN_ROLE = 'superadmin';

/**
 * Pure predicate over a parsed-JWT-claims object. True IFF either:
 *   - claims.email === 'admin@madfam.io', or
 *   - claims.role === 'superadmin' (singular — some IdPs use this), or
 *   - claims.roles contains 'superadmin' (plural — Janua's canonical shape).
 *
 * Default-deny invariant: any input shape we don't explicitly recognize
 * MUST return false. Unknown is not admin.
 */
export function isMadfamAdminClaims(claims: unknown): boolean {
  if (claims == null || typeof claims !== 'object') return false;
  const c = claims as Record<string, unknown>;

  // Email-based gate. Strict equality, lowercased input.
  const email = typeof c.email === 'string' ? c.email.trim().toLowerCase() : '';
  if (email === ADMIN_EMAIL) return true;

  // Singular `role` field (some IdPs use this shape).
  const singleRole = typeof c.role === 'string' ? c.role.trim().toLowerCase() : '';
  if (singleRole === SUPERADMIN_ROLE) return true;

  // Plural `roles` array (Janua's canonical shape).
  if (Array.isArray(c.roles)) {
    for (const r of c.roles) {
      if (typeof r === 'string' && r.trim().toLowerCase() === SUPERADMIN_ROLE) {
        return true;
      }
    }
  }

  return false;
}

/**
 * Platform-operator gate for server-verified claims: the MADFAM admin
 * predicate above, or Janua's `is_admin: true` (set from the Janua user's
 * system-admin flag in OIDC tokens).
 */
export function isPlatformAdminClaims(claims: unknown): boolean {
  if (isMadfamAdminClaims(claims)) return true;
  return (
    claims != null && typeof claims === 'object' && (claims as Record<string, unknown>).is_admin === true
  );
}
