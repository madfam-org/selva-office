// @vitest-environment node
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { SignJWT, createLocalJWKSet, exportJWK, generateKeyPair, type JWTVerifyGetKey, type KeyLike } from 'jose';
import { NextRequest } from 'next/server';

const jwksState = vi.hoisted(() => ({
  resolver: null as null | ((...args: unknown[]) => unknown),
}));

vi.mock('jose', async (importOriginal) => {
  const actual = await importOriginal<typeof import('jose')>();
  return {
    ...actual,
    createRemoteJWKSet: () => (...args: unknown[]) => {
      if (!jwksState.resolver) throw new Error('JWKS resolver not configured');
      return jwksState.resolver(...args);
    },
  };
});

import { GET, POST } from '../app/api/nexus/[...path]/route';
import { apiFetch } from '../lib/api';
import { middleware } from '../middleware';

const ISSUER = 'https://auth.example.test';
const CLIENT_ID = 'selva-admin-test';
const KID = 'admin-key-1';
const SECRET = 'test-session-secret-0123456789abcdef';

let signingKey: KeyLike;
let localJwks: JWTVerifyGetKey;
let fetchMock: ReturnType<typeof vi.fn>;

beforeAll(async () => {
  const pair = await generateKeyPair('RS256');
  signingKey = pair.privateKey;
  const jwk = await exportJWK(pair.publicKey);
  localJwks = createLocalJWKSet({ keys: [{ ...jwk, kid: KID, alg: 'RS256', use: 'sig' }] });
});

beforeEach(() => {
  vi.stubEnv('NEXT_PUBLIC_JANUA_ISSUER_URL', ISSUER);
  vi.stubEnv('JANUA_CLIENT_ID', CLIENT_ID);
  vi.stubEnv('JANUA_SECRET_KEY', '');
  vi.stubEnv('SESSION_SECRET', '');
  vi.stubEnv('NEXT_PUBLIC_NEXUS_API_URL', 'https://nexus.example.test');
  jwksState.resolver = (...args: unknown[]) =>
    (localJwks as (...a: unknown[]) => unknown)(...args);
  fetchMock = vi.fn(async () => Response.json({ ok: true }));
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

function januaToken(roles: string[] = ['admin']): Promise<string> {
  return new SignJWT({ sub: 'user-1', roles })
    .setProtectedHeader({ alg: 'RS256', kid: KID })
    .setIssuer(ISSUER)
    .setAudience(CLIENT_ID)
    .setExpirationTime('1h')
    .sign(signingKey);
}

function sessionToken(roles: string[] = ['admin']): Promise<string> {
  return new SignJWT({ sub: 'user-1', roles })
    .setProtectedHeader({ alg: 'HS256' })
    .setIssuer('selva-admin')
    .setExpirationTime('1h')
    .sign(new TextEncoder().encode(SECRET));
}

function req(path: string, cookies: Record<string, string> = {}, init: { method?: string; body?: string } = {}) {
  const headers = new Headers();
  const cookie = Object.entries(cookies)
    .map(([k, v]) => `${k}=${v}`)
    .join('; ');
  if (cookie) headers.set('cookie', cookie);
  return new NextRequest(new URL(path, 'https://admin.example.test'), { headers, ...init });
}

const ctx = (path: string[]) => ({ params: Promise.resolve({ path }) });

describe('admin /api/nexus proxy', () => {
  it('forwards the Janua session token when the session is the access token', async () => {
    const token = await januaToken();
    const res = await GET(req('/api/nexus/api/v1/agents', { 'janua-session': token }), ctx(['api', 'v1', 'agents']));
    expect(res.status).toBe(200);
    const [target, init] = fetchMock.mock.calls[0] as [URL, RequestInit];
    expect(target.toString()).toBe('https://nexus.example.test/api/v1/agents');
    expect((init.headers as Headers).get('authorization')).toBe(`Bearer ${token}`);
    expect((init.headers as Headers).get('cookie')).toBeNull();
  });

  it('forwards the access-token cookie, not the signed admin session, when sessions are signed', async () => {
    vi.stubEnv('JANUA_SECRET_KEY', SECRET);
    const access = await januaToken();
    await POST(
      req(
        '/api/nexus/api/v1/agents',
        { 'janua-session': await sessionToken(), 'janua-access-token': access },
        { method: 'POST', body: '{"name":"a"}' },
      ),
      ctx(['api', 'v1', 'agents']),
    );
    const [, init] = fetchMock.mock.calls[0] as [URL, RequestInit];
    expect((init.headers as Headers).get('authorization')).toBe(`Bearer ${access}`);
    expect(init.method).toBe('POST');
  });

  it('returns 401 for a signed session without an access-token cookie', async () => {
    vi.stubEnv('JANUA_SECRET_KEY', SECRET);
    const res = await GET(req('/api/nexus/api/v1/agents', { 'janua-session': await sessionToken() }), ctx(['api', 'v1', 'agents']));
    expect(res.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('returns 401 without calling Nexus for a missing or invalid session', async () => {
    for (const cookies of [{}, { 'janua-session': 'garbage' }] as Record<string, string>[]) {
      const res = await GET(req('/api/nexus/api/v1/agents', cookies), ctx(['api', 'v1', 'agents']));
      expect(res.status).toBe(401);
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('returns 403 without calling Nexus for a session without the admin role', async () => {
    const res = await GET(
      req('/api/nexus/api/v1/agents', { 'janua-session': await januaToken(['member']) }),
      ctx(['api', 'v1', 'agents']),
    );
    expect(res.status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('refuses paths outside /api/v1', async () => {
    const res = await GET(req('/api/nexus/x', { 'janua-session': await januaToken() }), ctx(['metrics']));
    expect(res.status).toBe(404);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe('admin apiFetch', () => {
  it('calls the same-origin proxy without an Authorization header', async () => {
    await apiFetch('/api/v1/agents');
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/nexus/api/v1/agents');
    expect(init.credentials).toBe('same-origin');
    expect((init.headers as Headers).get('authorization')).toBeNull();
  });
});

describe('admin middleware cookie cleanup', () => {
  it('clears both session cookies when the session does not verify', async () => {
    const res = await middleware(req('/agents', { 'janua-session': 'garbage', 'janua-access-token': 'x' }));
    const setCookie = res.headers.get('set-cookie') ?? '';
    expect(setCookie).toMatch(/janua-session=;/);
    expect(setCookie).toMatch(/janua-access-token=;/);
  });
});
