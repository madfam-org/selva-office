import { NextResponse, type NextRequest } from 'next/server';
import { CRAWL_FILE_PATHS } from '@/lib/seo/crawl';
import { SESSION_COOKIE, verifySessionToken } from '@/lib/verify-session';

/**
 * URL scheme:
 *   selva.town       → Landing page (public)
 *   app.selva.town   → Virtual office app (auth required for /office)
 */

const APP_HOST = 'app.selva.town';
const LANDING_HOST = 'selva.town';
const WWW_HOST = 'www.selva.town';

const PUBLIC_PATHS = [
  '/',
  '/login',
  '/guest',
  '/demo',
  '/pricing',
  '/api/health',
  '/api/auth',
  // robots.txt, sitemap.xml, llms.txt: public so the auth redirect never
  // answers them with the login page. They still pass the www redirect.
  ...CRAWL_FILE_PATHS,
];

function isPublicPath(pathname: string): boolean {
  return PUBLIC_PATHS.some(
    (pub) => pathname === pub || pathname.startsWith(`${pub}/`),
  );
}

function isApiPath(pathname: string): boolean {
  return pathname === '/api' || pathname.startsWith('/api/');
}

function isAppHost(host: string): boolean {
  return host === APP_HOST || host.startsWith(APP_HOST);
}

export async function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const host = request.headers.get('host') || '';

  // --- Canonical host (www.selva.town → selva.town) ---
  // Declared in infra as a 301, but the tunnel routes www at office-ui with
  // no redirect, so www served a duplicate of the apex (SEO split, cookie
  // scoping surprises). Redirect permanently, preserving path + query.
  if (host === WWW_HOST) {
    const url = request.nextUrl.clone();
    url.host = LANDING_HOST;
    url.port = '';
    return NextResponse.redirect(url, 301);
  }

  // --- App host (app.selva.town) ---
  // Redirect root to /office, allow /demo and /login as entry points
  if (isAppHost(host) && pathname === '/') {
    return NextResponse.redirect(new URL('/office', request.url));
  }

  if (isPublicPath(pathname)) {
    return NextResponse.next();
  }

  // Protected paths need a `janua-session` token that verifies against
  // Janua (signature, issuer, expiry, audience; see lib/verify-session.ts).
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  const session = await verifySessionToken(token);
  if (session.status === 'ok') {
    return NextResponse.next();
  }

  // The cookie is left in place: /demo keeps its own unsigned demo session
  // in it, and that page stays usable after a denied request elsewhere.
  if (isApiPath(pathname)) {
    return NextResponse.json(
      { error: 'unauthorized', detail: 'valid session required' },
      { status: 401, headers: { 'WWW-Authenticate': 'Bearer' } },
    );
  }
  const loginUrl = new URL('/login', request.url);
  loginUrl.searchParams.set('redirect', `${pathname}${search}`);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - _next/static (static files)
     * - _next/image (image optimization)
     * - favicon.ico (favicon)
     * - public folder assets
     */
    '/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)',
  ],
};
