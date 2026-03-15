'use client';

import { useState, useEffect, useCallback } from 'react';
import { apiFetch } from '@/lib/api';

interface ConnectedUser {
  session_id: string;
  name: string;
  status: string;
}

interface AdminPanelProps {
  isOpen: boolean;
  onClose: () => void;
  isAdmin: boolean;
}

/**
 * Admin panel for managing connected users and room configuration.
 * Only rendered when the user has the admin role.
 */
export function AdminPanel({ isOpen, onClose, isAdmin }: AdminPanelProps) {
  const [users, setUsers] = useState<ConnectedUser[]>([]);
  const [motd, setMotd] = useState('');
  const [loading, setLoading] = useState(false);

  const fetchUsers = useCallback(async () => {
    if (!isAdmin) return;
    try {
      const resp = await apiFetch('/api/v1/admin/users');
      if (resp.ok) {
        setUsers(await resp.json());
      }
    } catch {
      // Silently ignore — admin features are best-effort
    }
  }, [isAdmin]);

  useEffect(() => {
    if (isOpen && isAdmin) {
      fetchUsers();
    }
  }, [isOpen, isAdmin, fetchUsers]);

  const handleKick = useCallback(
    async (sessionId: string) => {
      setLoading(true);
      try {
        await apiFetch('/api/v1/admin/kick', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: sessionId }),
        });
        // Refresh list
        await fetchUsers();
      } catch {
        // ignore
      } finally {
        setLoading(false);
      }
    },
    [fetchUsers]
  );

  const handleMotdUpdate = useCallback(async () => {
    setLoading(true);
    try {
      await apiFetch('/api/v1/admin/room-config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ motd }),
      });
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [motd]);

  if (!isOpen || !isAdmin) return null;

  return (
    <div className="fixed right-0 top-0 h-full w-full max-w-80 sm:w-80 retro-panel z-modal animate-slide-in-right flex flex-col">
      <div className="flex items-center justify-between p-3 border-b border-slate-700">
        <h2 className="text-retro-base font-bold text-slate-200">Admin</h2>
        <button
          onClick={onClose}
          className="text-slate-400 hover:text-slate-200"
          aria-label="Close admin panel"
        >
          [X]
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-4">
        {/* Connected Users */}
        <section>
          <h3 className="text-retro-xs font-bold text-slate-300 mb-2">
            Connected Users ({users.length})
          </h3>
          <div className="space-y-1">
            {users.map((u) => (
              <div
                key={u.session_id}
                className="flex items-center justify-between p-2 rounded bg-slate-800/50"
              >
                <span className="text-retro-xs text-slate-200 truncate">
                  {u.name}
                </span>
                <button
                  onClick={() => handleKick(u.session_id)}
                  disabled={loading}
                  className="pxa-btn text-retro-xs px-2 py-0.5 bg-red-900/50 hover:bg-red-800/50"
                >
                  Kick
                </button>
              </div>
            ))}
          </div>
        </section>

        {/* Room Config */}
        <section>
          <h3 className="text-retro-xs font-bold text-slate-300 mb-2">
            Room Config
          </h3>
          <div className="space-y-2">
            <input
              type="text"
              value={motd}
              onChange={(e) => setMotd(e.target.value)}
              placeholder="Message of the day..."
              maxLength={500}
              className="pxa-input w-full text-retro-xs"
            />
            <button
              onClick={handleMotdUpdate}
              disabled={loading}
              className="pxa-btn text-retro-xs px-3 py-1 w-full"
            >
              Update MOTD
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}
