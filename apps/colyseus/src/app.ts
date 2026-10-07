import express from "express";

/**
 * The Express 4 app behind the room server's HTTP listener.
 *
 * Colyseus serves its matchmake routes first (they are bound inside
 * `server.listen()`, see index.ts) and hands everything else to this app.
 * It lives in its own module so tests can exercise the real route table
 * without starting the room server.
 */
export function createApp(): express.Express {
  const app = express();

  app.get("/health", (_req, res) => {
    res.json({ status: "healthy", service: "colyseus" });
  });

  return app;
}
