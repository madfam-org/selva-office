import type { Client } from "@colyseus/core";
import type { OfficeStateSchema } from "../schema/OfficeState";

const PROXIMITY_RADIUS = 200; // pixels
const MAX_PEERS = 6;

export interface ProximityGroup {
  sessionId: string;
  nearbySessionIds: string[];
}

/**
 * Calculate proximity groups for all connected players.
 * Returns a list indicating which players are near each other.
 */
export function calculateProximity(
  state: OfficeStateSchema
): ProximityGroup[] {
  const players = Array.from(state.players.entries()).map(
    ([sessionId, player]) => ({
      sessionId,
      x: player.x,
      y: player.y,
    })
  );

  const groups: ProximityGroup[] = [];

  for (const player of players) {
    const nearby: string[] = [];
    for (const other of players) {
      if (other.sessionId === player.sessionId) continue;
      const dx = player.x - other.x;
      const dy = player.y - other.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist <= PROXIMITY_RADIUS) {
        nearby.push(other.sessionId);
      }
    }
    // Limit to MAX_PEERS, sorted by distance
    const sorted = nearby
      .map((sid) => {
        const other = players.find((p) => p.sessionId === sid)!;
        const dx = player.x - other.x;
        const dy = player.y - other.y;
        return { sid, dist: Math.sqrt(dx * dx + dy * dy) };
      })
      .sort((a, b) => a.dist - b.dist)
      .slice(0, MAX_PEERS)
      .map((e) => e.sid);

    groups.push({ sessionId: player.sessionId, nearbySessionIds: sorted });
  }

  return groups;
}

/**
 * Start a proximity broadcast loop at the given frequency (Hz).
 * Returns a cleanup function to stop the loop.
 */
export function startProximityLoop(
  state: OfficeStateSchema,
  getClients: () => Client[],
  frequency: number = 5
): () => void {
  const intervalMs = 1000 / frequency;

  const interval = setInterval(() => {
    const groups = calculateProximity(state);
    const clients = getClients();

    for (const group of groups) {
      const client = clients.find(
        (c) => c.sessionId === group.sessionId
      );
      if (client) {
        client.send("proximity_players", {
          nearbySessionIds: group.nearbySessionIds,
        });
      }
    }
  }, intervalMs);

  return () => clearInterval(interval);
}
