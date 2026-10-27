// @vitest-environment node
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  SignJWT,
  createLocalJWKSet,
  exportJWK,
  generateKeyPair,
  type JWTPayload,
  type JWTVerifyGetKey,
  type KeyLike,
} from 'jose';
import { NextRequest } from 'next/server';

// Route Janua key lookups to a resolver the tests control (no network).
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

import { middleware } from '../middleware';
import { verifySessionToken } from '../lib/verify-session';
import { isPlatformAdminClaims } from '../lib/madfam-admin';
import { bundlesAccess } from '../app/bundles/access';
import { GET as proxyGet, POST as proxyPost } from '../app/api/nexus/[...path]/route';

const ISSUER = 'https://auth.example.test';
const CLIENT_ID = 'selva-office-test';
const PLATFORM_AUDIENCE = 'janua-platform';
const KID = 'office-key-1';

let signingKey: KeyLike;
let otherKey: KeyLike;
let localJwks: JWTVerifyGetKey;

beforeAll(async () => {
  const pair = await generateKeyPair('RS256');
  signingKey = pair.privateKey;
  const jwk = await exportJWK(pair.publicKey);
  localJwks = createLocalJWKSet({ keys: [{ ...jwk, kid: KID, alg: 'RS256', use: 'sig' }] });
  otherKey = (await generateKeyPair('RS256')).privateKey;
});

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.stubEnv('NEXT_PUBLIC_JANUA_ISSUER_URL', ISSUER);
  vi.stubEnv('NEXT_PUBLIC_JANUA_CLIENT_ID', CLIENT_ID);
  vi.stubEnv('NEXT_PUBLIC_API_URL', 'https://nexus.example.test');
  vi.stubEnv('DEV_AUTH_BYPASS', '');
  vi.stubEnv('NEXT_PUBLIC_DEV_AUTH_BYPASS', '');
  jwksState.resolver = (...args: unknown[]) =>
    (localJwks as (...a: unknown[]) => unknown)(...args);
  fetchMock = vi.fn(async () =>
    new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { 'Content-Type': 'application/json', 'Set-Cookie': 'upstream=1' },
    }),
  );
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

interface TokenOptions {
  claims?: JWTPayload;
  key?: KeyLike;
  issuer?: string;
  audience?: string;
  expiresIn?: string | number;
}

function token(opts: TokenOptions = {}): Promise<string> {
  return new SignJWT({ sub: 'user-1', roles: ['member'], ...opts.claims })
    .setProtectedHeader({ alg: 'RS256', kid: KID })
    .setIssuedAt()
    .setIssuer(opts.issuer ?? ISSUER)
    .setAudience(opts.audience ?? CLIENT_ID)
    .setExpirationTime(opts.expiresIn ?? '1h')
    .sign(opts.key ?? signingKey);
}

function guestToken(claims: JWTPayload = {}): Promise<string> {
  return token({
    audience: PLATFORM_AUDIENCE,
    claims: { roles: ['guest'], type: 'guest_access', org_id: 'org-1', ...claims },
  });
}

function unsigned(payload: JWTPayload): string {
  const enc = (o: object) => Buffer.from(JSON.stringify(o)).toString('base64url');
  return `${enc({ alg: 'none', typ: 'JWT' })}.${enc(payload)}.`;
}

function req(path: string, opts: { cookie?: string; authorization?: string; method?: string; body?: string } = {}) {
  const headers = new Headers({ host: 'app.selva.town' });
  if (opts.cookie !== undefined) headers.set('cookie', `janua-session=${opts.cookie}`);
  if (opts.authorization) headers.set('authorization', opts.authorization);
  if (opts.body) headers.set('content-type', 'application/json');
  return new NextRequest(new URL(path, 'https://app.selva.town'), {
    headers,
    method: opts.method,
    body: opts.body,
  });
}

const passed = (res: Response) => res.headers.get('x-middleware-next') === '1';

function expectLogin(res: Response, redirect: string) {
  expect(res.status).toBe(307);
  const loc = new URL(res.headers.get('location')!);
  expect(loc.pathname).toBe('/login');
  expect(loc.searchParams.get('redirect')).toBe(redirect);
}

function ctx(path: string[]) {
  return { params: Promise.resolve({ path }) };
}

describe('office-ui middleware session verification', () => {
  it('keeps public paths open', async () => {
    for (const path of ['/login', '/demo', '/guest', '/pricing', '/api/health', '/api/auth/login']) {
      expect(passed(await middleware(req(path)))).toBe(true);
    }
  });

  it('redirects a protected page without a token to /login with path and query', async () => {
    expectLogin(await middleware(req('/office?room=2')), '/office?room=2');
  });

  it('answers protected API paths without a token with 401 JSON', async () => {
    const res = await middleware(req('/api/nexus/api/v1/agents'));
    expect(res.status).toBe(401);
    expect(await res.json()).toMatchObject({ error: 'unauthorized' });
  });

  it('does not accept an Authorization header in place of the session cookie', async () => {
    expectLogin(await middleware(req('/office', { authorization: 'Bearer garbage' })), '/office');
    expectLogin(
      await middleware(req('/office', { authorization: `Bearer ${await token()}` })),
      '/office',
    );
  });

  it('denies malformed, unsigned, foreign-key, expired, wrong-issuer and wrong-audience tokens', async () => {
    const bad = [
      'not-a-jwt',
      unsigned({ sub: 'x', roles: ['admin'], iss: ISSUER, aud: CLIENT_ID, exp: 9999999999 }),
      await token({ key: otherKey }),
      await token({ expiresIn: Math.floor(Date.now() / 1000) - 3600 }),
      await token({ issuer: 'https://other.example.test' }),
      await token({ audience: 'another-client' }),
    ];
    for (const cookie of bad) {
      expectLogin(await middleware(req('/office', { cookie })), '/office');
    }
  });

  it('denies the request when key resolution throws', async () => {
    jwksState.resolver = () => {
      throw new Error('JWKS endpoint unreachable');
    };
    expectLogin(await middleware(req('/office', { cookie: await token() })), '/office');
  });

  it('does not clear the cookie on a denied request (the /demo session lives there)', async () => {
    const res = await middleware(req('/office', { cookie: unsigned({ org_id: 'demo-public', roles: ['demo'] }) }));
    expect(res.headers.get('set-cookie')).toBeNull();
  });

  it('lets a verified user token through', async () => {
    expect(passed(await middleware(req('/office', { cookie: await token() })))).toBe(true);
  });

  it('lets a verified Janua guest token through', async () => {
    expect(passed(await middleware(req('/office', { cookie: await guestToken() })))).toBe(true);
  });
});

describe('verifySessionToken', () => {
  it('classifies client-audience tokens as user sessions', async () => {
    const result = await verifySessionToken(await token({ claims: { roles: ['member'] } }));
    expect(result).toMatchObject({ status: 'ok', kind: 'user', roles: ['member'] });
  });

  it('accepts the platform audience only for an exact guest grant', async () => {
    expect(await verifySessionToken(await guestToken())).toMatchObject({ status: 'ok', kind: 'guest', roles: ['guest'] });
    expect(await verifySessionToken(await guestToken({ roles: ['guest', 'admin'] }))).toEqual({
      status: 'unauthenticated',
    });
    expect(await verifySessionToken(await guestToken({ type: 'access' }))).toEqual({
      status: 'unauthenticated',
    });
  });

  it('requires exp', async () => {
    const noExp = await new SignJWT({ sub: 'u' })
      .setProtectedHeader({ alg: 'RS256', kid: KID })
      .setIssuer(ISSUER)
      .setAudience(CLIENT_ID)
      .sign(signingKey);
    expect(await verifySessionToken(noExp)).toEqual({ status: 'unauthenticated' });
  });

  it('honours the development flag only under NODE_ENV=development', async () => {
    vi.stubEnv('DEV_AUTH_BYPASS', 'true');
    vi.stubEnv('NODE_ENV', 'production');
    expect(await verifySessionToken('dev.token.')).toEqual({ status: 'unauthenticated' });
    vi.stubEnv('NODE_ENV', 'development');
    expect(await verifySessionToken('dev.token.')).toMatchObject({ status: 'ok' });
    expect(await verifySessionToken(undefined)).toEqual({ status: 'unauthenticated' });
  });
});

describe('platform admin predicate', () => {
  it('does not treat a bare organization admin role as a platform admin', () => {
    expect(isPlatformAdminClaims({ roles: ['admin'] })).toBe(false);
    expect(isPlatformAdminClaims({ roles: ['owner', 'admin'], email: 'someone@example.com' })).toBe(false);
  });

  it('accepts superadmin, the MADFAM admin email, or Janua is_admin', () => {
    expect(isPlatformAdminClaims({ roles: ['superadmin'] })).toBe(true);
    expect(isPlatformAdminClaims({ email: 'admin@madfam.io' })).toBe(true);
    expect(isPlatformAdminClaims({ is_admin: true })).toBe(true);
    expect(isPlatformAdminClaims({ is_admin: 'true' })).toBe(false);
  });
});

describe('bundlesAccess', () => {
  it('returns unauthenticated for missing or invalid tokens', async () => {
    expect(await bundlesAccess(undefined)).toBe('unauthenticated');
    expect(await bundlesAccess(unsigned({ roles: ['superadmin'], exp: 9999999999 }))).toBe('unauthenticated');
    expect(await bundlesAccess(await token({ key: otherKey, claims: { is_admin: true } }))).toBe(
      'unauthenticated',
    );
  });

  it('returns forbidden for verified non-operators, including organization admins and guests', async () => {
    expect(await bundlesAccess(await token({ claims: { roles: ['member'] } }))).toBe('forbidden');
    expect(await bundlesAccess(await token({ claims: { roles: ['admin'] } }))).toBe('forbidden');
    expect(await bundlesAccess(await guestToken())).toBe('forbidden');
  });

  it('returns ok for verified platform operators', async () => {
    expect(await bundlesAccess(await token({ claims: { is_admin: true } }))).toBe('ok');
    expect(await bundlesAccess(await token({ claims: { roles: ['superadmin'] } }))).toBe('ok');
  });
});

describe('/api/nexus proxy', () => {
  it('forwards a verified session to Nexus with the token as a Bearer header', async () => {
    const session = await token();
    const res = await proxyGet(
      req('/api/nexus/api/v1/agents?limit=5', { cookie: session }),
      ctx(['api', 'v1', 'agents']),
    );

    expect(res.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [target, init] = fetchMock.mock.calls[0] as [URL, RequestInit];
    expect(target.toString()).toBe('https://nexus.example.test/api/v1/agents?limit=5');
    const headers = init.headers as Headers;
    expect(headers.get('authorization')).toBe(`Bearer ${session}`);
    expect(headers.get('cookie')).toBeNull();
    expect(init.redirect).toBe('manual');
    expect(res.headers.get('set-cookie')).toBeNull();
  });

  it('forwards method and body', async () => {
    const session = await token();
    await proxyPost(
      req('/api/nexus/api/v1/swarms/dispatch', { cookie: session, method: 'POST', body: '{"a":1}' }),
      ctx(['api', 'v1', 'swarms', 'dispatch']),
    );
    const [, init] = fetchMock.mock.calls[0] as [URL, RequestInit];
    expect(init.method).toBe('POST');
    expect(new TextDecoder().decode(init.body as ArrayBuffer)).toBe('{"a":1}');
  });

  it('returns 401 without calling Nexus when the session does not verify', async () => {
    for (const cookie of [undefined, 'garbage', await token({ key: otherKey })]) {
      const res = await proxyGet(req('/api/nexus/api/v1/agents', { cookie }), ctx(['api', 'v1', 'agents']));
      expect(res.status).toBe(401);
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('only forwards /api/v1 paths without dot segments', async () => {
    const session = await token();
    for (const path of [['health'], ['api', 'v2', 'x'], ['api', 'v1', '..', 'admin'], ['api', 'v1', 'a/b']]) {
      const res = await proxyGet(req('/api/nexus/x', { cookie: session }), ctx(path));
      expect(res.status).toBe(404);
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('answers 502 when Nexus is unreachable', async () => {
    fetchMock.mockRejectedValueOnce(new Error('ECONNREFUSED'));
    const res = await proxyGet(req('/api/nexus/api/v1/agents', { cookie: await token() }), ctx(['api', 'v1', 'agents']));
    expect(res.status).toBe(502);
  });
});
