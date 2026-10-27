import { isPlatformAdminClaims } from '@/lib/madfam-admin';
import { verifySessionToken } from '@/lib/verify-session';

export type BundlesAccess = 'ok' | 'forbidden' | 'unauthenticated';

/**
 * Access decision for /bundles, made on the verified session token itself
 * (lib/verify-session.ts) rather than on anything the middleware did.
 *
 * Bundles are a proposed pricing surface for MADFAM operators, so the gate is
 * the platform-admin predicate (lib/madfam-admin.ts), not the bare `admin`
 * role, which Janua also emits for admins of any customer organization.
 */
export async function bundlesAccess(token: string | null | undefined): Promise<BundlesAccess> {
  const session = await verifySessionToken(token);
  if (session.status !== 'ok') return 'unauthenticated';
  if (session.kind !== 'user' || !isPlatformAdminClaims(session.claims)) return 'forbidden';
  return 'ok';
}
