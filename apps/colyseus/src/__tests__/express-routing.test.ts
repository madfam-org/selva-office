import * as fs from "node:fs";
import * as path from "node:path";
import { once } from "node:events";
import type { Server } from "node:http";
import { createRequire } from "node:module";
import type { AddressInfo } from "node:net";
import express from "express";
import { describe, it, expect } from "vitest";
import { createApp } from "../app";

/**
 * Guards the root `pnpm.overrides` entry `express@4>path-to-regexp`.
 *
 * This server runs Express 4, whose router compiles every route with
 * path-to-regexp 0.1.x, so the override keeps that copy at or above 0.1.13
 * (CVE-2026-4867). It is scoped to Express 4 on purpose: a blanket
 * `path-to-regexp` override also reaches Express 5's `router@2`, which needs
 * 8.x (see apps/office-ui/src/__tests__/express5-routing.test.ts).
 */

type Require = ReturnType<typeof createRequire>;

const requireHere = createRequire(__filename);

/** Version of `name` as `from` resolves it (works for packages that do not export package.json). */
function installedVersion(name: string, from: Require): string {
  let dir = path.dirname(from.resolve(name));
  for (;;) {
    const manifest = path.join(dir, "package.json");
    if (fs.existsSync(manifest)) {
      const pkg = JSON.parse(fs.readFileSync(manifest, "utf8")) as { name?: string; version: string };
      if (pkg.name === name) return pkg.version;
    }
    const parent = path.dirname(dir);
    if (parent === dir) throw new Error(`no package.json found for ${name}`);
    dir = parent;
  }
}

async function withServer(app: express.Express, run: (base: string) => Promise<void>): Promise<void> {
  const server: Server = app.listen(0, "127.0.0.1");
  await once(server, "listening");
  try {
    const { port } = server.address() as AddressInfo;
    await run(`http://127.0.0.1:${port}`);
  } finally {
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
}

describe("Express 4 routing (colyseus server)", () => {
  it("runs Express 4 on a patched path-to-regexp 0.1.x", () => {
    expect(installedVersion("express", requireHere)).toMatch(/^4\./);

    const fromExpress = createRequire(requireHere.resolve("express"));
    const [major, minor, patch] = installedVersion("path-to-regexp", fromExpress)
      .split(".")
      .map(Number);
    expect([major, minor]).toEqual([0, 1]);
    expect(patch).toBeGreaterThanOrEqual(13);
  });

  it("serves /health from the server's own app", async () => {
    await withServer(createApp(), async (base) => {
      const res = await fetch(`${base}/health`);
      expect(res.status).toBe(200);
      expect(await res.json()).toEqual({ status: "healthy", service: "colyseus" });

      expect((await fetch(`${base}/no-such-route`)).status).toBe(404);
    });
  });

  it("matches parameterised routes", async () => {
    const app = express();
    app.get("/rooms/:roomId", (req, res) => {
      res.json({ roomId: req.params.roomId });
    });

    await withServer(app, async (base) => {
      const res = await fetch(`${base}/rooms/office-1`);
      expect(res.status).toBe(200);
      expect(await res.json()).toEqual({ roomId: "office-1" });
    });
  });
});
