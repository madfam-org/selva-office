import { NextResponse, type NextRequest } from 'next/server';
import { logger } from '@/lib/logger';
import {
  CALLBACK_PATH,
  OAUTH_FLOW_COOKIE,
  constantTimeEqual,
  decodeFlowState,
  flowCookieOptions,
  getOrigin,
  januaClientId,
  januaIssuerUrl,
  safeRedirectPath,
} from '@/lib/janua-oauth';

function clearFlowCookie(response: NextResponse): NextResponse {
  response.cookies.set(OAUTH_FLOW_COOKIE, '', flowCookieOptions(0));
  return response;
}

function loginError(origin: string, code: string): NextResponse {
  return clearFlowCookie(
    NextResponse.redirect(`${origin}/login?sso_error=${encodeURIComponent(code)}`),
  );
}

/**
 * GET /api/auth/callback/janua
 *
 * OAuth 2.0 Authorization Code callback with PKCE (public client).
 * 1. Requires the `state` parameter to match the value stored by
 *    /api/auth/login in the httpOnly flow cookie, then deletes the cookie
 * 2. Exchanges the authorization code using the stored PKCE verifier
 * 3. Stores the access token as an httpOnly session cookie
 * 4. Redirects to the stored same-origin post-login path
 */
export async function GET(request: NextRequest) {
  const url = request.nextUrl;
  const origin = getOrigin(request);
  const code = url.searchParams.get('code');
  const state = url.searchParams.get('state');
  const error = url.searchParams.get('error');

  if (error) {
    const desc = url.searchParams.get('error_description') || error;
    return loginError(origin, desc);
  }

  if (!code) {
    return loginError(origin, 'Missing authorization code');
  }

  const flow = decodeFlowState(request.cookies.get(OAUTH_FLOW_COOKIE)?.value);
  if (!flow || !state || !constantTimeEqual(state, flow.state)) {
    logger.warn('OAuth callback: state check failed');
    return loginError(origin, 'invalid_state');
  }

  const tokenParams = new URLSearchParams({
    grant_type: 'authorization_code',
    code,
    redirect_uri: `${origin}${CALLBACK_PATH}`,
    client_id: januaClientId(),
    code_verifier: flow.verifier,
  });

  let tokenData: { access_token: string; expires_in?: number };

  try {
    const tokenRes = await fetch(`${januaIssuerUrl()}/api/v1/oauth/token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: tokenParams,
    });

    if (!tokenRes.ok) {
      const body = await tokenRes.text();
      logger.error('Token exchange failed:', tokenRes.status, body);
      return loginError(origin, 'Token exchange failed');
    }

    tokenData = await tokenRes.json();
  } catch (err) {
    logger.error('Token exchange error:', err);
    return loginError(origin, 'Auth server unreachable');
  }

  if (!tokenData?.access_token) {
    return loginError(origin, 'Token exchange failed');
  }

  const response = clearFlowCookie(
    NextResponse.redirect(`${origin}${safeRedirectPath(flow.redirect)}`),
  );

  // The office-ui middleware checks this cookie for protected routes.
  const expiresIn = tokenData.expires_in || 86400;
  response.cookies.set('janua-session', tokenData.access_token, {
    httpOnly: true,
    secure: true,
    sameSite: 'lax',
    path: '/',
    maxAge: expiresIn,
  });

  return response;
}
