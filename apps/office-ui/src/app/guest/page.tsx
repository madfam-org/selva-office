'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { FormEvent, Suspense, useCallback, useState } from 'react';

const JANUA_URL =
  process.env.NEXT_PUBLIC_JANUA_ISSUER_URL ?? '';
const DEFAULT_ORG = process.env.NEXT_PUBLIC_GUEST_DEFAULT_ORG ?? '';
const GUEST_ENABLED = process.env.NEXT_PUBLIC_GUEST_ACCESS_ENABLED !== 'false';

type GuestState = 'idle' | 'validating' | 'joining' | 'error';

interface InviteInfo {
  org_name: string;
  room_id?: string;
}

function GuestJoinForm() {
  const router = useRouter();
  const params = useSearchParams();
  const inviteToken = params.get('invite') ?? '';

  const [displayName, setDisplayName] = useState('');
  const [state, setState] = useState<GuestState>(inviteToken ? 'validating' : 'idle');
  const [error, setError] = useState('');
  const [inviteInfo, setInviteInfo] = useState<InviteInfo | null>(null);

  // Validate invite token on mount if present
  const validateInvite = useCallback(async () => {
    if (!inviteToken) return;
    try {
      const resp = await fetch(
        `${JANUA_URL}/api/v1/auth/guest/validate/${inviteToken}`,
      );
      if (resp.ok) {
        const data = await resp.json();
        setInviteInfo({ org_name: data.org_name, room_id: data.room_id });
        setState('idle');
      } else {
        setState('error');
        setError('This invite link is invalid or has expired.');
      }
    } catch {
      setState('error');
      setError('Unable to validate invite. Please try again.');
    }
  }, [inviteToken]);

  // Validate on first render
  useState(() => {
    if (inviteToken) validateInvite();
  });

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!displayName.trim()) return;
    setState('joining');
    setError('');

    try {
      const body: Record<string, unknown> = {
        display_name: displayName.trim(),
      };
      if (inviteToken) {
        body.invite_token = inviteToken;
      } else if (DEFAULT_ORG) {
        body.org_id = DEFAULT_ORG;
      }

      const resp = await fetch(`${JANUA_URL}/api/v1/auth/guest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'Request failed' }));
        throw new Error(err.detail ?? `HTTP ${resp.status}`);
      }

      const data = await resp.json();

      // Set the session cookie
      document.cookie = `janua-session=${data.access_token}; path=/; max-age=${4 * 3600}; SameSite=Lax`;

      // Redirect to the office
      router.push('/');
    } catch (err) {
      setState('error');
      setError(err instanceof Error ? err.message : 'Failed to join as guest');
    }
  };

  if (!GUEST_ENABLED) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950">
        <div className="retro-panel p-8 text-center">
          <h1 className="text-retro-lg text-white mb-4">Guest Access Disabled</h1>
          <p className="text-retro-sm text-slate-400 mb-6">
            Guest access is not enabled for this instance.
          </p>
          <a href="/login" className="retro-btn px-4 py-2 text-retro-sm">
            Go to Login
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950">
      <div className="retro-panel p-8 w-full max-w-sm">
        <h1 className="text-retro-lg text-white mb-2 text-center">
          Join as Guest
        </h1>
        {inviteInfo && (
          <p className="text-retro-xs text-indigo-400 text-center mb-4">
            Invited to {inviteInfo.org_name}
          </p>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label
              htmlFor="displayName"
              className="block text-retro-xs text-slate-400 mb-1"
            >
              Display Name
            </label>
            <input
              id="displayName"
              name="displayName"
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="Enter your name"
              maxLength={50}
              required
              autoFocus
              className="w-full px-3 py-2 bg-slate-800 border border-slate-600 text-white text-retro-sm rounded focus:border-indigo-500 focus:outline-none"
            />
          </div>

          {error && (
            <p className="text-retro-xs text-red-400">{error}</p>
          )}

          <button
            type="submit"
            disabled={state === 'joining' || state === 'validating'}
            className="retro-btn w-full px-4 py-2 text-retro-sm disabled:opacity-50"
          >
            {state === 'joining'
              ? 'Joining...'
              : state === 'validating'
                ? 'Validating invite...'
                : 'Join Office'}
          </button>
        </form>

        <div className="mt-6 text-center">
          <a
            href="/login"
            className="text-retro-xs text-slate-500 hover:text-indigo-400 transition-colors"
          >
            Have an account? Sign in
          </a>
        </div>
      </div>
    </div>
  );
}

export default function GuestPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-slate-950">
          <p className="text-retro-sm text-slate-400">Loading...</p>
        </div>
      }
    >
      <GuestJoinForm />
    </Suspense>
  );
}
