import type { NextRequest } from 'next/server';
import { proxyToNexus } from '@/lib/nexus-proxy';
import { SESSION_COOKIE, verifySessionToken } from '@/lib/verify-session';

/**
 * /api/nexus/api/v1/... → Nexus API /api/v1/..., with the session token from
 * the httpOnly `janua-session` cookie attached as a Bearer header.
 * See lib/nexus-proxy.ts.
 */

export const dynamic = 'force-dynamic';

function upstreamBase(): string {
  return process.env.NEXT_PUBLIC_API_URL || process.env.NEXUS_API_URL || 'http://localhost:4300';
}

type RouteContext = { params: Promise<{ path?: string[] }> };

async function handle(request: NextRequest, context: RouteContext): Promise<Response> {
  const { path } = await context.params;
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  const session = await verifySessionToken(token);
  return proxyToNexus(request, path, {
    upstreamBase: upstreamBase(),
    token: session.status === 'ok' ? token : null,
  });
}

export const GET = handle;
export const POST = handle;
export const PUT = handle;
export const PATCH = handle;
export const DELETE = handle;
