// @vitest-environment node
import * as fs from 'node:fs';
import * as path from 'node:path';
import { once } from 'node:events';
import type { Server } from 'node:http';
import { createRequire } from 'node:module';
import type { AddressInfo } from 'node:net';
import { describe, it, expect } from 'vitest';

/**
 * Guards the root `pnpm.overrides` entry `router@2>path-to-regexp`, and the
 * absence of a blanket `path-to-regexp` pin.
 *
 * office-ui never imports Express, but `@colyseus/sdk` installs
 * `@colyseus/core` as an optional dependency, and that copy of core resolves
 * Express 5 (shadcn's MCP SDK resolves the same Express 5 at the root).
 * Express 5 routes through `router@2`, which needs path-to-regexp 8.x. While
 * the root pinned every path-to-regexp to 0.1.13 (the Express 4 line),
 * registering any Express 5 route threw `pathRegexp.match is not a function`.
 * The 8.x floor is 8.4.0 (CVE-2026-4926, CVE-2026-4923).
 */

type Require = ReturnType<typeof createRequire>;
type Handler = (
  req: { params: Record<string, string | string[]> },
  res: { json: (body: unknown) => void },
) => void;
type Express5App = {
  get: (route: string, handler: Handler) => unknown;
  listen: (port: number, host: string) => Server;
};

const requireHere = createRequire(import.meta.url);
const fromSdk = createRequire(requireHere.resolve('@colyseus/sdk/package.json'));
const fromCore = createRequire(fromSdk.resolve('@colyseus/core/package.json'));

/** Version of `name` as `from` resolves it (works for packages that do not export package.json). */
function installedVersion(name: string, from: Require): string {
  let dir = path.dirname(from.resolve(name));
  for (;;) {
    const manifest = path.join(dir, 'package.json');
    if (fs.existsSync(manifest)) {
      const pkg = JSON.parse(fs.readFileSync(manifest, 'utf8')) as {
        name?: string;
        version: string;
      };
      if (pkg.name === name) return pkg.version;
    }
    const parent = path.dirname(dir);
    if (parent === dir) throw new Error(`no package.json found for ${name}`);
    dir = parent;
  }
}

describe('Express 5 routing (via @colyseus/sdk -> @colyseus/core)', () => {
  it('resolves Express 5 from the @colyseus/core copy office-ui installs', () => {
    expect(installedVersion('express', fromCore)).toMatch(/^5\./);
  });

  it('gives router@2 a path-to-regexp 8.x at or above 8.4.0', () => {
    const fromExpress = createRequire(fromCore.resolve('express'));
    const fromRouter = createRequire(fromExpress.resolve('router'));
    expect(installedVersion('router', fromExpress)).toMatch(/^2\./);

    const [major, minor] = installedVersion('path-to-regexp', fromRouter).split('.').map(Number);
    expect(major).toBe(8);
    expect(minor).toBeGreaterThanOrEqual(4);
  });

  it('registers and matches Express 5 routes', async () => {
    const express = fromCore('express') as () => Express5App;
    const app = express();
    app.get('/rooms/:roomId', (req, res) => res.json({ roomId: req.params.roomId }));
    app.get('/files/*rest', (req, res) => res.json({ rest: req.params.rest }));

    const server = app.listen(0, '127.0.0.1');
    await once(server, 'listening');
    try {
      const { port } = server.address() as AddressInfo;
      const base = `http://127.0.0.1:${port}`;

      const room = await fetch(`${base}/rooms/office-1`);
      expect(room.status).toBe(200);
      expect(await room.json()).toEqual({ roomId: 'office-1' });

      const file = await fetch(`${base}/files/maps/office.json`);
      expect(file.status).toBe(200);
      expect(await file.json()).toEqual({ rest: ['maps', 'office.json'] });

      expect((await fetch(`${base}/no-such-route`)).status).toBe(404);
    } finally {
      await new Promise<void>((resolve) => server.close(() => resolve()));
    }
  });
});
