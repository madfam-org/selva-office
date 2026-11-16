import { describe, it, expect } from 'vitest';
import { isMadfamAdminClaims } from '../useIsMadfamAdmin';

describe('isMadfamAdminClaims — default-deny gate', () => {
  it('returns false for null', () => {
    expect(isMadfamAdminClaims(null)).toBe(false);
  });

  it('returns false for undefined', () => {
    expect(isMadfamAdminClaims(undefined)).toBe(false);
  });

  it('returns false for non-objects', () => {
    expect(isMadfamAdminClaims('admin@madfam.io')).toBe(false);
    expect(isMadfamAdminClaims(42)).toBe(false);
    expect(isMadfamAdminClaims(true)).toBe(false);
  });

  it('returns false for empty objects', () => {
    expect(isMadfamAdminClaims({})).toBe(false);
  });

  it('returns true only for is_admin exactly true', () => {
    expect(isMadfamAdminClaims({ is_admin: true })).toBe(true);
    expect(isMadfamAdminClaims({ is_admin: 'true' })).toBe(false);
    expect(isMadfamAdminClaims({ is_admin: 1 })).toBe(false);
    expect(isMadfamAdminClaims({ is_admin: false })).toBe(false);
  });

  it('ignores role names and email addresses', () => {
    expect(isMadfamAdminClaims({ email: 'admin@example.com' })).toBe(false);
    expect(isMadfamAdminClaims({ role: 'superadmin' })).toBe(false);
    expect(isMadfamAdminClaims({ roles: ['user', 'superadmin'] })).toBe(false);
    expect(isMadfamAdminClaims({ roles: ['owner', 'admin'] })).toBe(false);
    expect(isMadfamAdminClaims({ roles: ['selva:admin'] })).toBe(false);
  });

  it('default-denies when the claims shape is unknown', () => {
    // Some adversarial-looking shapes that should NOT slip through.
    expect(isMadfamAdminClaims({ admin: true })).toBe(false);
    expect(isMadfamAdminClaims({ isAdmin: true })).toBe(false);
    expect(isMadfamAdminClaims({ permissions: ['*'] })).toBe(false);
  });
});
