'use client';

export const dynamic = 'force-dynamic';

import { useSearchParams, useRouter } from 'next/navigation';
import { useCallback } from 'react';

const DUMMY_JWT_PAYLOAD =
  'eyJzdWIiOiJkZXYtdXNlciIsInJvbGVzIjpbImFkbWluIiwidGFjdGljaWFuIl0sIm9yZ19pZCI6ImRldi1vcmciLCJlbWFpbCI6ImRldkBhdXRvc3dhcm0ubG9jYWwiLCJuYW1lIjoiRGV2IFVzZXIifQ==';

/** Dev-only header + payload (no signature). Good enough for local work. */
const DUMMY_JWT = `eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.${DUMMY_JWT_PAYLOAD}.`;

const JANUA_ISSUER_URL = process.env.NEXT_PUBLIC_JANUA_ISSUER_URL ?? '';
const JANUA_CLIENT_ID = process.env.NEXT_PUBLIC_JANUA_CLIENT_ID ?? 'autoswarm-office';

export default function LoginPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const redirect = searchParams.get('redirect') ?? '/';

  const handleDevLogin = useCallback(() => {
    document.cookie = `janua-session=${DUMMY_JWT}; path=/; max-age=86400; SameSite=Lax`;
    router.push(redirect);
  }, [redirect, router]);

  const handleJanuaLogin = useCallback(() => {
    const callbackUrl = `${window.location.origin}/api/auth/callback/janua`;
    const params = new URLSearchParams({
      client_id: JANUA_CLIENT_ID,
      redirect_uri: callbackUrl,
      response_type: 'code',
      scope: 'openid profile email',
      state: redirect,
    });
    window.location.href = `${JANUA_ISSUER_URL}/authorize?${params.toString()}`;
  }, [redirect]);

  const hasJanua = Boolean(JANUA_ISSUER_URL);

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-950 px-4">
      <div className="w-full max-w-sm rounded-2xl border border-gray-800 bg-gray-900 p-8 shadow-xl">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-bold tracking-tight text-white">AutoSwarm Office</h1>
          <p className="mt-1 text-sm text-gray-400">
            {hasJanua ? 'Sign in to continue' : 'Development Login'}
          </p>
        </div>

        {hasJanua ? (
          <>
            <button
              type="button"
              onClick={handleJanuaLogin}
              className="w-full rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-gray-900"
            >
              Sign in with Janua
            </button>
            <button
              type="button"
              onClick={handleDevLogin}
              className="mt-3 w-full rounded-lg border border-gray-700 px-4 py-2.5 text-sm font-medium text-gray-400 transition-colors hover:bg-gray-800 hover:text-white focus:outline-none focus:ring-2 focus:ring-gray-500 focus:ring-offset-2 focus:ring-offset-gray-900"
            >
              Dev Login (bypass)
            </button>
          </>
        ) : (
          <button
            type="button"
            onClick={handleDevLogin}
            className="w-full rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-gray-900"
          >
            Login as Dev User
          </button>
        )}

        <p className="mt-6 text-center text-xs text-gray-500">
          {hasJanua
            ? 'Powered by Janua SSO'
            : 'Set NEXT_PUBLIC_JANUA_ISSUER_URL to enable SSO'}
        </p>
      </div>
    </main>
  );
}
