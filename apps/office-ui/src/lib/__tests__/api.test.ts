import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { apiFetch, getSessionUser } from '../api';

describe('apiFetch', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    });
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    // Clear any cookie we set
    if (typeof document !== 'undefined') {
      document.cookie = 'janua-session=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
    }
  });

  it('calls fetch with API base URL + path', async () => {
    await apiFetch('/api/v1/health');

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/health'),
      expect.any(Object),
    );
  });

  it('includes credentials: include', async () => {
    await apiFetch('/api/v1/test');

    expect(fetchMock).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ credentials: 'include' }),
    );
  });

  it('sets Content-Type to application/json', async () => {
    await apiFetch('/api/v1/test');

    const callArgs = fetchMock.mock.calls[0];
    const headers = callArgs[1].headers as Headers;
    expect(headers.get('Content-Type')).toBe('application/json');
  });

  it('passes through method and body', async () => {
    const body = JSON.stringify({ key: 'value' });

    await apiFetch('/api/v1/test', { method: 'POST', body });

    const callArgs = fetchMock.mock.calls[0];
    expect(callArgs[1].method).toBe('POST');
    expect(callArgs[1].body).toBe(body);
  });

  it('attaches Authorization header when janua-session cookie is set', async () => {
    document.cookie = 'janua-session=my-test-token';

    await apiFetch('/api/v1/test');

    const callArgs = fetchMock.mock.calls[0];
    const headers = callArgs[1].headers as Headers;
    expect(headers.get('Authorization')).toBe('Bearer my-test-token');
  });

  it('does not attach Authorization header when no cookie is set', async () => {
    // Ensure cookie is cleared
    document.cookie = 'janua-session=; expires=Thu, 01 Jan 1970 00:00:00 GMT';

    await apiFetch('/api/v1/test');

    const callArgs = fetchMock.mock.calls[0];
    const headers = callArgs[1].headers as Headers;
    expect(headers.get('Authorization')).toBeNull();
  });
});

describe('getSessionUser', () => {
  afterEach(() => {
    if (typeof document !== 'undefined') {
      document.cookie = 'janua-session=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
    }
  });

  it('returns null when no cookie is set', () => {
    document.cookie = 'janua-session=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
    expect(getSessionUser()).toBeNull();
  });

  it('parses a valid JWT cookie and returns user claims', () => {
    const payload = {
      sub: 'user-123',
      email: 'test@example.com',
      name: 'Test User',
      roles: ['admin'],
    };
    const encoded = btoa(JSON.stringify(payload));
    const fakeJwt = `header.${encoded}.signature`;

    document.cookie = `janua-session=${fakeJwt}`;

    const user = getSessionUser();
    expect(user).toEqual({
      sub: 'user-123',
      email: 'test@example.com',
      name: 'Test User',
      roles: ['admin'],
    });
  });

  it('returns defaults for missing claims', () => {
    const payload = {}; // no sub, email, name, roles
    const encoded = btoa(JSON.stringify(payload));
    const fakeJwt = `header.${encoded}.signature`;

    document.cookie = `janua-session=${fakeJwt}`;

    const user = getSessionUser();
    expect(user).toEqual({
      sub: '',
      email: '',
      name: undefined,
      roles: [],
    });
  });

  it('returns null for malformed JWT (too few parts)', () => {
    document.cookie = 'janua-session=not-a-jwt';

    expect(getSessionUser()).toBeNull();
  });

  it('returns null for invalid base64 payload', () => {
    document.cookie = 'janua-session=header.!!!invalid!!!.signature';

    expect(getSessionUser()).toBeNull();
  });
});
