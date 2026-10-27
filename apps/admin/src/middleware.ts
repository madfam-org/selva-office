import { NextResponse, type NextRequest } from 'next/server';
import { ADMIN_ACCESS_TOKEN_COOKIE, ADMIN_SESSION_COOKIE } from '@/lib/janua-config';
import { checkAdminSession } from '@/lib/verify-session';

const PUBLIC_PATHS = ['/login', '/api/health', '/api/auth'];

function isPublicPath(pathname: string): boolean {
  return PUBLIC_PATHS.some(
    (pub) => pathname === pub || pathname.startsWith(`${pub}/`),
  );
}

function isApiPath(pathname: string): boolean {
  return pathname === '/api' || pathname.startsWith('/api/');
}

/**
 * Admin access gate. Every non-public request needs a `janua-session` cookie
 * whose token verifies (signature, issuer, audience, expiry; see
 * lib/verify-session.ts) and carries the `admin` role.
 *
 *   - missing / invalid / expired token: pages redirect to /login, /api/* get 401
 *   - valid token without the admin role: 403
 */
export async function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  if (isPublicPath(pathname)) {
    return NextResponse.next();
  }

  const token = request.cookies.get(ADMIN_SESSION_COOKIE)?.value;
  const session = await checkAdminSession(token);

  if (session.status === 'ok') {
    return NextResponse.next();
  }

  if (session.status === 'forbidden') {
    return isApiPath(pathname)
      ? NextResponse.json({ error: 'forbidden', detail: 'admin role required' }, { status: 403 })
      : new NextResponse('Forbidden: admin role required', { status: 403 });
  }

  let response: NextResponse;
  if (isApiPath(pathname)) {
    response = NextResponse.json(
      { error: 'unauthorized', detail: 'valid admin session required' },
      { status: 401, headers: { 'WWW-Authenticate': 'Bearer' } },
    );
  } else {
    const loginUrl = new URL('/login', request.url);
    loginUrl.searchParams.set('redirect', `${pathname}${search}`);
    response = NextResponse.redirect(loginUrl);
  }

  // Drop a session cookie that did not verify so the browser stops sending it.
  if (token) {
    response.cookies.delete(ADMIN_SESSION_COOKIE);
    response.cookies.delete(ADMIN_ACCESS_TOKEN_COOKIE);
  }
  return response;
}

export const config = {
  matcher: [
    '/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)',
  ],
};
