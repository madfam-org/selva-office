// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { jwtVerify, type JWTPayload } from 'jose';
import { NextRequest } from 'next/server';
import { GET } from '../app/api/auth/callback/route';
import { adminRolesFromJanuaClaims } from '../lib/verify-session';

const ISSUER = 'https://auth.example.test';
const CLIENT_ID = 'autoswarm-office';
const SECRET = 'test-session-secret-0123456789abcdef';

/** Janua access tokens are RS256; the callback only decodes them. */
function accessToken(payload: JWTPayload): string {
  const enc = (o: object) => Buffer.from(JSON.stringify(o)).toString('base64url');
  return `${enc({ alg: 'RS256', typ: 'JWT' })}.${enc(payload)}.sig`;
}

let fetchMock: ReturnType<typeof vi.fn>;

function stubJanua(claims: JWTPayload, userinfoSub = 'user-1') {
  fetchMock.mockImplementation(async (url: string) => {
    if (url.endsWith('/api/v1/oauth/token')) {
      return Response.json({
        access_token: accessToken({ sub: 'user-1', aud: 'janua.dev', ...claims }),
        token_type: 'Bearer',
        expires_in: 3600,
      });
    }
    if (url.endsWith('/api/v1/oauth/userinfo')) {
      return Response.json({ sub: userinfoSub, email: 'ops@example.test', name: 'Ops' });
    }
    throw new Error(`unexpected fetch ${url}`);
  });
}

function callback(): NextRequest {
  return new NextRequest('https://admin.example.test/api/auth/callback?code=c0de&state=st4te', {
    headers: { cookie: 'oauth_state=st4te; oauth_code_verifier=v3rifier; oauth_redirect=%2Fbilling' },
  });
}

async function sessionClaims(res: Response & { cookies: { get(name: string): { value: string } | undefined } }) {
  const token = res.cookies.get('janua-session')?.value;
  expect(token).toBeTruthy();
  const { payload } = await jwtVerify(token!, new TextEncoder().encode(SECRET), { issuer: 'selva-admin' });
  return payload;
}

beforeEach(() => {
  vi.stubEnv('NEXT_PUBLIC_JANUA_BASE_URL', ISSUER);
  vi.stubEnv('JANUA_CLIENT_ID', CLIENT_ID);
  vi.stubEnv('JANUA_SECRET_KEY', SECRET);
  fetchMock = vi.fn();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe('adminRolesFromJanuaClaims', () => {
  it.each([
    [{ is_admin: true }, ['admin']],
    [{ is_admin: true, roles: ['member'] }, ['admin']],
    [{ roles: ['selva:admin'] }, ['admin']],
    [{ roles: 'member,selva:admin' }, ['admin']],
  ])('grants the console for %j', (claims, expected) => {
    expect(adminRolesFromJanuaClaims(claims)).toEqual(expected);
  });

  it.each([
    {},
    { roles: ['admin'] },
    { roles: ['owner', 'admin'] },
    { role: 'admin' },
    { is_admin: 'true' },
    { is_admin: false, roles: ['hcm:admin'] },
  ])('refuses %j (organization roles are not Selva roles)', (claims) => {
    expect(adminRolesFromJanuaClaims(claims as JWTPayload)).toEqual([]);
  });
});

describe('GET /api/auth/callback', () => {
  it('exchanges the code with the configured client and signs an admin session for a platform admin', async () => {
    stubJanua({ is_admin: true, roles: ['member'], org_id: 'org-1' });

    const res = await GET(callback());

    expect(res.status).toBe(307);
    expect(new URL(res.headers.get('location')!).pathname).toBe('/billing');
    const tokenBody = new URLSearchParams(fetchMock.mock.calls[0][1].body as URLSearchParams);
    expect(tokenBody.get('client_id')).toBe(CLIENT_ID);
    expect(tokenBody.get('code_verifier')).toBe('v3rifier');
    const claims = await sessionClaims(res);
    expect(claims).toMatchObject({ sub: 'user-1', roles: ['admin'], org_id: 'org-1', email: 'ops@example.test' });
    expect(res.cookies.get('janua-access-token')?.value).toBeTruthy();
  });

  it('signs a session without the admin role for an organization admin', async () => {
    stubJanua({ roles: ['owner', 'admin'] });

    const res = await GET(callback());

    expect(res.status).toBe(307);
    expect((await sessionClaims(res)).roles).toEqual([]);
  });

  it('refuses a token whose subject differs from userinfo', async () => {
    stubJanua({ is_admin: true }, 'someone-else');

    const res = await GET(callback());

    const location = new URL(res.headers.get('location')!);
    expect(location.pathname).toBe('/login');
    expect(location.searchParams.get('error')).toBe('Failed to retrieve user information');
    expect(res.cookies.get('janua-session')).toBeUndefined();
  });
});
