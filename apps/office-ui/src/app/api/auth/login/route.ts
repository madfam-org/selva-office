import { NextResponse, type NextRequest } from 'next/server';
import {
  CALLBACK_PATH,
  OAUTH_FLOW_COOKIE,
  encodeFlowState,
  flowCookieOptions,
  getOrigin,
  januaClientId,
  januaIssuerUrl,
  pkceChallenge,
  randomToken,
  safeRedirectPath,
} from '@/lib/janua-oauth';

/**
 * GET /api/auth/login?redirect=/office
 *
 * Starts the Janua authorization-code + PKCE flow. The `state` value and the
 * PKCE verifier stay server-side in an httpOnly cookie that the callback
 * checks before exchanging the code.
 */
export async function GET(request: NextRequest) {
  const origin = getOrigin(request);
  const redirect = safeRedirectPath(request.nextUrl.searchParams.get('redirect'));

  const state = randomToken(32);
  const verifier = randomToken(32);
  const challenge = await pkceChallenge(verifier);

  const params = new URLSearchParams({
    client_id: januaClientId(),
    redirect_uri: `${origin}${CALLBACK_PATH}`,
    response_type: 'code',
    scope: 'openid profile email',
    state,
    code_challenge: challenge,
    code_challenge_method: 'S256',
  });

  const response = NextResponse.redirect(
    `${januaIssuerUrl()}/api/v1/oauth/authorize?${params.toString()}`,
  );
  response.cookies.set(
    OAUTH_FLOW_COOKIE,
    encodeFlowState({ state, verifier, redirect }),
    flowCookieOptions(),
  );
  response.headers.set('Cache-Control', 'no-store');
  return response;
}
