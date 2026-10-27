// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';
import { GET as login } from '../app/api/auth/login/route';
import { GET as callback } from '../app/api/auth/callback/janua/route';
import {
  OAUTH_FLOW_COOKIE,
  constantTimeEqual,
  decodeFlowState,
  encodeFlowState,
  pkceChallenge,
  randomToken,
  safeRedirectPath,
  type OAuthFlowState,
} from '../lib/janua-oauth';

const ORIGIN = 'https://app.selva.test';
const ISSUER = 'https://auth.example.test';

function requestTo(path: string, cookies: Record<string, string> = {}): NextRequest {
  const headers = new Headers({ host: 'app.selva.test', 'x-forwarded-proto': 'https' });
  const cookie = Object.entries(cookies)
    .map(([k, v]) => `${k}=${v}`)
    .join('; ');
  if (cookie) headers.set('cookie', cookie);
  return new NextRequest(new URL(path, ORIGIN), { headers });
}

function flowCookieFrom(res: Response): string | null {
  const header = res.headers.get('set-cookie') ?? '';
  const match = header.match(new RegExp(`${OAUTH_FLOW_COOKIE}=([^;]*)`));
  return match ? match[1] : null;
}

function makeFlow(overrides: Partial<OAuthFlowState> = {}): OAuthFlowState {
  return { state: randomToken(32), verifier: randomToken(32), redirect: '/office', ...overrides };
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.stubEnv('NEXT_PUBLIC_JANUA_ISSUER_URL', ISSUER);
  vi.stubEnv('NEXT_PUBLIC_JANUA_CLIENT_ID', 'selva-office-test');
  fetchMock = vi.fn(async () =>
    new Response(JSON.stringify({ access_token: 'access-token-value', expires_in: 3600 }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  );
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe('GET /api/auth/login', () => {
  it('redirects to Janua with a random state and S256 challenge, and stores the flow in an httpOnly cookie', async () => {
    const res = await login(requestTo('/api/auth/login?redirect=%2Foffice%3Froom%3D2'));
    expect(res.status).toBe(307);

    const authorize = new URL(res.headers.get('location')!);
    expect(`${authorize.origin}${authorize.pathname}`).toBe(`${ISSUER}/api/v1/oauth/authorize`);
    expect(authorize.searchParams.get('client_id')).toBe('selva-office-test');
    expect(authorize.searchParams.get('redirect_uri')).toBe(`${ORIGIN}/api/auth/callback/janua`);
    expect(authorize.searchParams.get('code_challenge_method')).toBe('S256');

    const state = authorize.searchParams.get('state')!;
    expect(state).not.toContain('/');
    expect(state.length).toBeGreaterThanOrEqual(43); // 32 bytes base64url

    const setCookie = res.headers.get('set-cookie')!;
    expect(setCookie).toMatch(/HttpOnly/i);
    expect(setCookie).toMatch(/Secure/i);
    expect(setCookie).toMatch(/SameSite=lax/i);
    expect(setCookie).toMatch(/Max-Age=600/i);
    expect(setCookie).toMatch(/Path=\//);

    const flow = decodeFlowState(flowCookieFrom(res));
    expect(flow).not.toBeNull();
    expect(flow!.state).toBe(state);
    expect(flow!.redirect).toBe('/office?room=2');
    expect(authorize.searchParams.get('code_challenge')).toBe(await pkceChallenge(flow!.verifier));
  });

  it('generates a different state on each request', async () => {
    const a = new URL((await login(requestTo('/api/auth/login'))).headers.get('location')!);
    const b = new URL((await login(requestTo('/api/auth/login'))).headers.get('location')!);
    expect(a.searchParams.get('state')).not.toBe(b.searchParams.get('state'));
  });

  it('stores the default path when the redirect target is not a same-origin relative path', async () => {
    const res = await login(requestTo('/api/auth/login?redirect=https%3A%2F%2Fexample.com%2F'));
    expect(decodeFlowState(flowCookieFrom(res))!.redirect).toBe('/office');
  });
});

describe('GET /api/auth/callback/janua', () => {
  it('rejects a callback with no flow cookie without calling the token endpoint', async () => {
    const res = await callback(requestTo('/api/auth/callback/janua?code=abc&state=whatever'));
    const location = new URL(res.headers.get('location')!);
    expect(location.pathname).toBe('/login');
    expect(location.searchParams.get('sso_error')).toBe('invalid_state');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('rejects a mismatched state without calling the token endpoint and clears the flow cookie', async () => {
    const flow = makeFlow();
    const res = await callback(
      requestTo(`/api/auth/callback/janua?code=abc&state=${randomToken(32)}`, {
        [OAUTH_FLOW_COOKIE]: encodeFlowState(flow),
      }),
    );
    expect(new URL(res.headers.get('location')!).searchParams.get('sso_error')).toBe('invalid_state');
    expect(fetchMock).not.toHaveBeenCalled();
    expect(res.headers.get('set-cookie')).toMatch(new RegExp(`${OAUTH_FLOW_COOKIE}=;`));
    expect(res.headers.get('set-cookie')).not.toMatch(/janua-session=/);
  });

  it('rejects a missing state parameter', async () => {
    const flow = makeFlow();
    const res = await callback(
      requestTo('/api/auth/callback/janua?code=abc', { [OAUTH_FLOW_COOKIE]: encodeFlowState(flow) }),
    );
    expect(new URL(res.headers.get('location')!).searchParams.get('sso_error')).toBe('invalid_state');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('rejects a malformed flow cookie', async () => {
    const res = await callback(
      requestTo('/api/auth/callback/janua?code=abc&state=x', { [OAUTH_FLOW_COOKIE]: 'garbage' }),
    );
    expect(new URL(res.headers.get('location')!).searchParams.get('sso_error')).toBe('invalid_state');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('exchanges the code with the stored verifier when the state matches', async () => {
    const flow = makeFlow({ redirect: '/office?room=2' });
    const res = await callback(
      requestTo(`/api/auth/callback/janua?code=abc&state=${flow.state}`, {
        [OAUTH_FLOW_COOKIE]: encodeFlowState(flow),
      }),
    );

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [tokenUrl, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(tokenUrl).toBe(`${ISSUER}/api/v1/oauth/token`);
    const body = new URLSearchParams(init.body as URLSearchParams);
    expect(body.get('code')).toBe('abc');
    expect(body.get('code_verifier')).toBe(flow.verifier);
    expect(body.get('redirect_uri')).toBe(`${ORIGIN}/api/auth/callback/janua`);

    expect(res.headers.get('location')).toBe(`${ORIGIN}/office?room=2`);
    const setCookie = res.headers.get('set-cookie')!;
    expect(setCookie).toMatch(/janua-session=access-token-value/);
    expect(setCookie).toMatch(new RegExp(`${OAUTH_FLOW_COOKIE}=;`));
    expect(setCookie).not.toMatch(/janua-sso-tokens/);
  });

  it('falls back to /office when the stored redirect is not a same-origin path', async () => {
    const flow = makeFlow({ redirect: '//example.com/phish' });
    const res = await callback(
      requestTo(`/api/auth/callback/janua?code=abc&state=${flow.state}`, {
        [OAUTH_FLOW_COOKIE]: encodeFlowState(flow),
      }),
    );
    expect(res.headers.get('location')).toBe(`${ORIGIN}/office`);
  });

  it('reports a provider error without calling the token endpoint', async () => {
    const res = await callback(requestTo('/api/auth/callback/janua?error=access_denied'));
    expect(new URL(res.headers.get('location')!).searchParams.get('sso_error')).toBe('access_denied');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('sends the user back to /login when the token exchange fails', async () => {
    fetchMock.mockResolvedValueOnce(new Response('nope', { status: 400 }));
    const flow = makeFlow();
    const res = await callback(
      requestTo(`/api/auth/callback/janua?code=abc&state=${flow.state}`, {
        [OAUTH_FLOW_COOKIE]: encodeFlowState(flow),
      }),
    );
    expect(new URL(res.headers.get('location')!).pathname).toBe('/login');
    expect(res.headers.get('set-cookie')).not.toMatch(/janua-session=/);
  });
});

describe('safeRedirectPath', () => {
  it.each([
    ['/office', '/office'],
    ['/office?room=2#desk', '/office?room=2#desk'],
    ['/a/../b', '/b'],
  ])('keeps the same-origin path %s', (input, expected) => {
    expect(safeRedirectPath(input)).toBe(expected);
  });

  it.each([
    null,
    '',
    'office',
    'https://example.com/',
    '//example.com/path',
    '/\\example.com',
    '/\texample',
    'javascript:alert(1)',
  ])('falls back to /office for %s', (input) => {
    expect(safeRedirectPath(input as string | null)).toBe('/office');
  });
});

describe('constantTimeEqual', () => {
  it('compares strings', () => {
    expect(constantTimeEqual('abc', 'abc')).toBe(true);
    expect(constantTimeEqual('abc', 'abd')).toBe(false);
    expect(constantTimeEqual('abc', 'abcd')).toBe(false);
    expect(constantTimeEqual('', '')).toBe(true);
  });
});

describe('flow state encoding', () => {
  it('round-trips and rejects incomplete values', () => {
    const flow = makeFlow();
    expect(decodeFlowState(encodeFlowState(flow))).toEqual(flow);
    expect(decodeFlowState(encodeFlowState({ ...flow, state: 'short' }))).toBeNull();
    expect(decodeFlowState(undefined)).toBeNull();
    expect(decodeFlowState('%%%')).toBeNull();
  });
});
