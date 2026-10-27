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

// The middleware resolves Janua's keys through createRemoteJWKSet; route it to
// a resolver the tests control so no network is involved.
const jwksState = vi.hoisted(() => ({
  resolver: null as null | ((...args: unknown[]) => unknown),
  remoteUrls: [] as string[],
}));

vi.mock('jose', async (importOriginal) => {
  const actual = await importOriginal<typeof import('jose')>();
  return {
    ...actual,
    createRemoteJWKSet: (url: URL) => {
      jwksState.remoteUrls.push(url.toString());
      return (...args: unknown[]) => {
        if (!jwksState.resolver) throw new Error('JWKS resolver not configured');
        return jwksState.resolver(...args);
      };
    },
  };
});

import { middleware } from '../middleware';
import { extractRoles } from '../lib/verify-session';

const ISSUER = 'https://auth.example.test';
const CLIENT_ID = 'selva-admin-test';
const KID = 'test-key-1';

let signingKey: KeyLike;
let otherKey: KeyLike;
let localJwks: JWTVerifyGetKey;

beforeAll(async () => {
  const pair = await generateKeyPair('RS256');
  signingKey = pair.privateKey;
  const publicJwk = await exportJWK(pair.publicKey);
  localJwks = createLocalJWKSet({ keys: [{ ...publicJwk, kid: KID, alg: 'RS256', use: 'sig' }] });
  otherKey = (await generateKeyPair('RS256')).privateKey;
});

beforeEach(() => {
  vi.stubEnv('NEXT_PUBLIC_JANUA_ISSUER_URL', ISSUER);
  vi.stubEnv('JANUA_CLIENT_ID', CLIENT_ID);
  vi.stubEnv('JANUA_SECRET_KEY', '');
  vi.stubEnv('SESSION_SECRET', '');
  vi.stubEnv('DEV_AUTH_BYPASS', '');
  jwksState.resolver = (...args: unknown[]) =>
    (localJwks as (...a: unknown[]) => unknown)(...args);
});

afterEach(() => {
  vi.unstubAllEnvs();
});

interface TokenOptions {
  claims?: JWTPayload;
  key?: KeyLike;
  kid?: string;
  issuer?: string;
  audience?: string;
  expiresIn?: string | number;
}

function januaToken(opts: TokenOptions = {}): Promise<string> {
  const jwt = new SignJWT({ sub: 'user-1', roles: ['admin'], ...opts.claims })
    .setProtectedHeader({ alg: 'RS256', kid: opts.kid ?? KID })
    .setIssuedAt()
    .setIssuer(opts.issuer ?? ISSUER)
    .setAudience(opts.audience ?? CLIENT_ID)
    .setExpirationTime(opts.expiresIn ?? '1h');
  return jwt.sign(opts.key ?? signingKey);
}

function sessionToken(secret: string, claims: JWTPayload = { roles: ['admin'] }, issuer = 'selva-admin') {
  return new SignJWT({ sub: 'user-1', ...claims })
    .setProtectedHeader({ alg: 'HS256' })
    .setIssuedAt()
    .setIssuer(issuer)
    .setExpirationTime('1h')
    .sign(new TextEncoder().encode(secret));
}

function unsignedToken(payload: JWTPayload): string {
  const enc = (o: object) => Buffer.from(JSON.stringify(o)).toString('base64url');
  return `${enc({ alg: 'none', typ: 'JWT' })}.${enc(payload)}.`;
}

function request(path: string, init: { cookie?: string; authorization?: string } = {}): NextRequest {
  const headers = new Headers();
  if (init.cookie !== undefined) headers.set('cookie', `janua-session=${init.cookie}`);
  if (init.authorization) headers.set('authorization', init.authorization);
  return new NextRequest(new URL(path, 'https://admin.example.test'), { headers });
}

function passedThrough(res: Response): boolean {
  return res.headers.get('x-middleware-next') === '1';
}

function expectLoginRedirect(res: Response, redirect: string) {
  expect(res.status).toBe(307);
  const location = new URL(res.headers.get('location')!);
  expect(location.pathname).toBe('/login');
  expect(location.searchParams.get('redirect')).toBe(redirect);
}

describe('admin middleware: public paths', () => {
  it.each(['/login', '/api/health', '/api/auth/sso', '/api/auth/callback'])(
    'lets %s through without a session',
    async (path) => {
      const res = await middleware(request(path));
      expect(passedThrough(res)).toBe(true);
    },
  );
});

describe('admin middleware: unauthenticated requests', () => {
  it('redirects a page request without a token to /login, keeping path and query', async () => {
    const res = await middleware(request('/agents?tab=active'));
    expectLoginRedirect(res, '/agents?tab=active');
  });

  it('answers an API request without a token with 401 JSON', async () => {
    const res = await middleware(request('/api/agents'));
    expect(res.status).toBe(401);
    expect(await res.json()).toMatchObject({ error: 'unauthorized' });
  });

  it('does not accept an Authorization header in place of the session cookie', async () => {
    const page = await middleware(request('/agents', { authorization: 'Bearer garbage' }));
    expectLoginRedirect(page, '/agents');

    const api = await middleware(request('/api/agents', { authorization: 'Bearer garbage' }));
    expect(api.status).toBe(401);
  });

  it('does not accept a valid Janua token sent only as a Bearer header', async () => {
    const token = await januaToken();
    const res = await middleware(request('/agents', { authorization: `Bearer ${token}` }));
    expectLoginRedirect(res, '/agents');
  });

  it('denies a malformed session cookie and clears it', async () => {
    const res = await middleware(request('/agents', { cookie: 'not-a-jwt' }));
    expectLoginRedirect(res, '/agents');
    expect(res.headers.get('set-cookie')).toMatch(/janua-session=;/);
  });

  it('denies an unsigned token that claims the admin role', async () => {
    const token = unsignedToken({
      sub: 'user-1',
      roles: ['admin'],
      iss: ISSUER,
      aud: CLIENT_ID,
      exp: Math.floor(Date.now() / 1000) + 3600,
    });
    const res = await middleware(request('/agents', { cookie: token }));
    expectLoginRedirect(res, '/agents');
  });

  it('denies an admin-role token signed by a key outside the JWKS', async () => {
    const token = await januaToken({ key: otherKey });
    const res = await middleware(request('/agents', { cookie: token }));
    expectLoginRedirect(res, '/agents');
  });

  it('denies an HS256 token when sessions are verified against the JWKS', async () => {
    const token = await sessionToken('some-shared-secret');
    const res = await middleware(request('/agents', { cookie: token }));
    expectLoginRedirect(res, '/agents');
  });

  it('denies an expired token', async () => {
    const token = await januaToken({ expiresIn: Math.floor(Date.now() / 1000) - 3600 });
    const res = await middleware(request('/agents', { cookie: token }));
    expectLoginRedirect(res, '/agents');
  });

  it('denies a token without an exp claim', async () => {
    const token = await new SignJWT({ sub: 'user-1', roles: ['admin'] })
      .setProtectedHeader({ alg: 'RS256', kid: KID })
      .setIssuer(ISSUER)
      .setAudience(CLIENT_ID)
      .sign(signingKey);
    const res = await middleware(request('/agents', { cookie: token }));
    expectLoginRedirect(res, '/agents');
  });

  it('denies a token from another issuer', async () => {
    const token = await januaToken({ issuer: 'https://other-issuer.example.test' });
    const res = await middleware(request('/agents', { cookie: token }));
    expectLoginRedirect(res, '/agents');
  });

  it('denies a token issued for another client', async () => {
    const token = await januaToken({ audience: 'some-other-client' });
    const res = await middleware(request('/agents', { cookie: token }));
    expectLoginRedirect(res, '/agents');
  });

  it('denies the request when key resolution throws', async () => {
    jwksState.resolver = () => {
      throw new Error('JWKS endpoint unreachable');
    };
    const token = await januaToken();
    const page = await middleware(request('/agents', { cookie: token }));
    expectLoginRedirect(page, '/agents');

    const api = await middleware(request('/api/agents', { cookie: token }));
    expect(api.status).toBe(401);
  });
});

describe('admin middleware: verified sessions', () => {
  it('returns 403 for a valid token without the admin role', async () => {
    const token = await januaToken({ claims: { roles: ['tactician'] } });
    const res = await middleware(request('/agents', { cookie: token }));
    expect(res.status).toBe(403);
    expect(passedThrough(res)).toBe(false);
  });

  it('returns 403 JSON on API paths for a valid token without the admin role', async () => {
    const token = await januaToken({ claims: { roles: [] } });
    const res = await middleware(request('/api/agents', { cookie: token }));
    expect(res.status).toBe(403);
    expect(await res.json()).toMatchObject({ error: 'forbidden' });
  });

  it('lets a valid admin token through', async () => {
    const token = await januaToken();
    const res = await middleware(request('/agents', { cookie: token }));
    expect(passedThrough(res)).toBe(true);
  });

  it('accepts the admin role given as a single string', async () => {
    const token = await januaToken({ claims: { roles: undefined, role: 'admin' } });
    const res = await middleware(request('/', { cookie: token }));
    expect(passedThrough(res)).toBe(true);
  });

  it('fetches keys from the issuer JWKS endpoint', async () => {
    const token = await januaToken();
    await middleware(request('/agents', { cookie: token }));
    expect(jwksState.remoteUrls).toContain(`${ISSUER}/.well-known/jwks.json`);
  });
});

describe('admin middleware: signed admin sessions (JANUA_SECRET_KEY set)', () => {
  const SECRET = 'test-session-secret-0123456789abcdef';

  beforeEach(() => {
    vi.stubEnv('JANUA_SECRET_KEY', SECRET);
  });

  it('lets a selva-admin session with the admin role through', async () => {
    const token = await sessionToken(SECRET);
    const res = await middleware(request('/agents', { cookie: token }));
    expect(passedThrough(res)).toBe(true);
  });

  it('returns 403 for a selva-admin session without the admin role', async () => {
    const token = await sessionToken(SECRET, { roles: ['viewer'] });
    const res = await middleware(request('/agents', { cookie: token }));
    expect(res.status).toBe(403);
  });

  it('denies a session signed with a different secret', async () => {
    const token = await sessionToken('a-different-secret-0123456789abcdef');
    const res = await middleware(request('/agents', { cookie: token }));
    expectLoginRedirect(res, '/agents');
  });

  it('denies a session with the wrong issuer', async () => {
    const token = await sessionToken(SECRET, { roles: ['admin'] }, 'someone-else');
    const res = await middleware(request('/agents', { cookie: token }));
    expectLoginRedirect(res, '/agents');
  });

  it('only accepts the session kind the callback issues in this mode', async () => {
    const token = await januaToken();
    const res = await middleware(request('/agents', { cookie: token }));
    expectLoginRedirect(res, '/agents');
  });
});

describe('admin middleware: development flag', () => {
  it('ignores DEV_AUTH_BYPASS outside NODE_ENV=development', async () => {
    vi.stubEnv('DEV_AUTH_BYPASS', 'true');
    vi.stubEnv('NODE_ENV', 'production');
    const token = unsignedToken({ sub: 'dev-user', roles: ['admin'] });
    const res = await middleware(request('/agents', { cookie: token }));
    expectLoginRedirect(res, '/agents');
  });

  it('honours DEV_AUTH_BYPASS only with NODE_ENV=development and a session cookie', async () => {
    vi.stubEnv('DEV_AUTH_BYPASS', 'true');
    vi.stubEnv('NODE_ENV', 'development');
    const token = unsignedToken({ sub: 'dev-user', roles: ['admin'] });
    expect(passedThrough(await middleware(request('/agents', { cookie: token })))).toBe(true);
    expectLoginRedirect(await middleware(request('/agents')), '/agents');
  });
});

describe('extractRoles', () => {
  it('reads arrays, single strings and comma-separated strings', () => {
    expect(extractRoles({ roles: ['admin', 'tactician'] })).toEqual(['admin', 'tactician']);
    expect(extractRoles({ role: 'admin' })).toEqual(['admin']);
    expect(extractRoles({ roles: 'viewer, admin' })).toEqual(['viewer', 'admin']);
    expect(extractRoles({ roles: [1, null, 'admin'] })).toEqual(['admin']);
    expect(extractRoles({})).toEqual([]);
  });
});
