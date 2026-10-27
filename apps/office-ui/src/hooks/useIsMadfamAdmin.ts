'use client';

/**
 * useIsMadfamAdmin — default-deny admin gate for the Atrium.
 *
 * Reads the Janua session cookie (decoded by `getSessionUser`) and
 * returns `true` IFF either:
 *   - claims.email === 'admin@madfam.io', or
 *   - claims.role === 'superadmin' (singular — some IdPs use this), or
 *   - claims.roles contains 'superadmin' (plural — Janua's canonical
 *     shape).
 *
 * Any deviation — missing token, malformed token, parse failure,
 * unknown claim shape — resolves to `false`. There is no SSR fallback
 * (the cookie is browser-only); during SSR we return `false` as well.
 *
 * SECURITY NOTE: this is UI-side gating only. The real authorization
 * boundary is the target service (Janua, Karafiel admin, etc.) which
 * re-validates the JWT on every request. The hook exists so we don't
 * render admin entry points for users who clearly aren't admins, not
 * to enforce authorization.
 */

import { useEffect, useState } from 'react';
import { getSessionUser } from '@/lib/api';
import { isMadfamAdminClaims } from '@/lib/madfam-admin';

// The predicate lives in a plain module so server code can use it too.
export { isMadfamAdminClaims };

export function useIsMadfamAdmin(): boolean {
  // SSR-safe: start as false. Even if this flickers for a frame on
  // hydration, default-deny means we never accidentally show admin
  // surfaces to a user who turned out not to be an admin.
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    try {
      const user = getSessionUser();
      setIsAdmin(isMadfamAdminClaims(user));
    } catch {
      setIsAdmin(false);
    }
  }, []);

  return isAdmin;
}
