/**
 * Same-origin proxy to the Nexus API.
 *
 * The session token lives in an httpOnly cookie that browser JS cannot read,
 * so `apiFetch` (lib/api.ts) calls `/api/nexus/<nexus path>` on this origin
 * and the route handler attaches `Authorization: Bearer <token>` server-side.
 *
 * Only `/api/v1/...` paths are forwarded, to one fixed upstream; cookies are
 * never forwarded upstream and upstream `Set-Cookie` headers are dropped.
 */

export const NEXUS_PROXY_PREFIX = '/api/nexus';

/** Request headers never forwarded upstream. */
const DROPPED_REQUEST_HEADERS = new Set([
  'authorization',
  'cookie',
  'host',
  'connection',
  'keep-alive',
  'proxy-authorization',
  'proxy-connection',
  'te',
  'trailer',
  'transfer-encoding',
  'upgrade',
  'content-length',
  'accept-encoding',
  'origin',
  'referer',
]);

/** Response headers never passed back to the browser. */
const DROPPED_RESPONSE_HEADERS = new Set([
  'set-cookie',
  'connection',
  'keep-alive',
  'transfer-encoding',
  'content-encoding',
  'content-length',
]);

/**
 * Map the catch-all segments to an upstream path, or null when the path is
 * outside `/api/v1/` or contains dot segments / empty segments.
 */
export function upstreamPath(segments: string[] | undefined): string | null {
  if (!segments || segments.length < 3) return null;
  if (segments[0] !== 'api' || segments[1] !== 'v1') return null;
  for (const segment of segments) {
    if (!segment || segment === '.' || segment === '..') return null;
    if (segment.includes('/') || segment.includes('\\')) return null;
  }
  return `/${segments.map(encodeURIComponent).join('/')}`;
}

export interface ProxyOptions {
  upstreamBase: string;
  token: string | null | undefined;
}

export async function proxyToNexus(
  request: Request,
  segments: string[] | undefined,
  { upstreamBase, token }: ProxyOptions,
): Promise<Response> {
  const path = upstreamPath(segments);
  if (!path) {
    return Response.json({ error: 'not_found' }, { status: 404 });
  }
  if (!token) {
    return Response.json(
      { error: 'unauthorized', detail: 'valid session required' },
      { status: 401, headers: { 'WWW-Authenticate': 'Bearer' } },
    );
  }

  const incoming = new URL(request.url);
  const target = new URL(`${upstreamBase.replace(/\/+$/, '')}${path}`);
  target.search = incoming.search;

  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (!DROPPED_REQUEST_HEADERS.has(key.toLowerCase())) headers.set(key, value);
  });
  headers.set('Authorization', `Bearer ${token}`);

  const method = request.method.toUpperCase();
  const hasBody = method !== 'GET' && method !== 'HEAD';

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method,
      headers,
      body: hasBody ? await request.arrayBuffer() : undefined,
      redirect: 'manual',
      cache: 'no-store',
    });
  } catch {
    return Response.json({ error: 'upstream_unavailable' }, { status: 502 });
  }

  const responseHeaders = new Headers();
  upstream.headers.forEach((value, key) => {
    if (!DROPPED_RESPONSE_HEADERS.has(key.toLowerCase())) responseHeaders.set(key, value);
  });
  responseHeaders.set('Cache-Control', 'no-store');

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  });
}
