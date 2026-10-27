import { NextResponse, type NextRequest } from 'next/server';
import {
  ADMIN_ACCESS_TOKEN_COOKIE,
  ADMIN_SESSION_COOKIE,
  adminSessionSecret,
} from '@/lib/janua-config';
import { proxyToNexus } from '@/lib/nexus-proxy';
import { checkAdminSession } from '@/lib/verify-session';

/**
 * /api/nexus/api/v1/... → Nexus API /api/v1/..., for verified admin sessions.
 * The Janua access token is attached server-side as a Bearer header:
 *   - signed admin session: from the httpOnly `janua-access-token` cookie
 *   - otherwise the session cookie itself is the Janua access token
 * See lib/nexus-proxy.ts.
 */

export const dynamic = 'force-dynamic';

function upstreamBase(): string {
  return (
    process.env.NEXT_PUBLIC_NEXUS_API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    process.env.NEXUS_API_URL ||
    'http://localhost:4300'
  );
}

type RouteContext = { params: Promise<{ path?: string[] }> };

async function handle(request: NextRequest, context: RouteContext): Promise<Response> {
  const { path } = await context.params;
  const sessionToken = request.cookies.get(ADMIN_SESSION_COOKIE)?.value;
  const session = await checkAdminSession(sessionToken);

  if (session.status === 'forbidden') {
    return NextResponse.json({ error: 'forbidden', detail: 'admin role required' }, { status: 403 });
  }

  let bearer: string | null = null;
  if (session.status === 'ok') {
    bearer = adminSessionSecret()
      ? (request.cookies.get(ADMIN_ACCESS_TOKEN_COOKIE)?.value ?? null)
      : (sessionToken ?? null);
  }

  return proxyToNexus(request, path, { upstreamBase: upstreamBase(), token: bearer });
}

export const GET = handle;
export const POST = handle;
export const PUT = handle;
export const PATCH = handle;
export const DELETE = handle;
