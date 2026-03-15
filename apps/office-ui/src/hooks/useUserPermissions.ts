'use client';

import { useMemo } from 'react';
import { getSessionUser } from '@/lib/api';

export interface UserPermissions {
  /** Can dispatch new swarm tasks. */
  canDispatchTasks: boolean;
  /** Can approve or deny approval requests. */
  canApproveOrDeny: boolean;
  /** Can create/edit/delete workflows. */
  canEditWorkflows: boolean;
  /** Can create/edit/delete maps. */
  canEditMaps: boolean;
  /** Can publish/rate/install marketplace skills. */
  canUseMarketplace: boolean;
  /** Can use the megaphone broadcast feature. */
  canUseMegaphone: boolean;
  /** Can start a spotlight presentation. */
  canUseSpotlight: boolean;
  /** Can connect/disconnect calendars. */
  canManageCalendar: boolean;
  /** Can access admin panel features. */
  isAdmin: boolean;
  /** Current user is a guest. */
  isGuest: boolean;
  /** Display name for the current user. */
  displayName: string;
}

/**
 * Derives UI permission flags from the current JWT session claims.
 *
 * Guest users (roles includes "guest") are restricted from write/privileged
 * operations while retaining read/observe access.
 */
export function useUserPermissions(): UserPermissions {
  return useMemo(() => {
    const user = getSessionUser();
    const roles = user?.roles ?? [];
    const guest = roles.includes('guest');
    const admin = roles.includes('admin');

    return {
      canDispatchTasks: !guest,
      canApproveOrDeny: !guest,
      canEditWorkflows: !guest,
      canEditMaps: !guest,
      canUseMarketplace: !guest,
      canUseMegaphone: !guest,
      canUseSpotlight: !guest,
      canManageCalendar: !guest,
      isAdmin: admin,
      isGuest: guest,
      displayName: user?.name ?? user?.email ?? 'Player',
    };
  }, []);
}
