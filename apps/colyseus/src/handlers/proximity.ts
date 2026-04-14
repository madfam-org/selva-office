import type { Client } from "@colyseus/core";
import type { OfficeStateSchema } from "../schema/OfficeState";
import { getMegaphoneSpeaker } from "./megaphone";

const PROXIMITY_RADIUS = 200; // pixels
const MAX_PEERS = 6;

export interface ProximityGroup {
  sessionId: string;
  nearbySessionIds: string[];
}

/**
 * Locked bubble groups. When a player locks their bubble, all currently
 * nearby players form a locked group. Members only see each other,
 * not outsiders, even if new players walk into proximity range.
 */
const lockedGroups = new Map<string, Set<string>>();

/** Find which locked group a session belongs to (if any). */
function findLockedGroup(sessionId: string): Set<string> | null {
  for (const group of lockedGroups.values()) {
    if (group.has(sessionId)) return group;
  }
  return null;
}

/**
 * Lock the current proximity bubble for a player.
 * All currently nearby players (including the requester) form a locked group.
 */
export function lockBubble(
  sessionId: string,
  state: OfficeStateSchema,
): boolean {
  // Already in a locked group
  if (findLockedGroup(sessionId)) return false;

  // Calculate who is currently nearby
  const groups = calculateProximity(state);
  const myGroup = groups.find((g) => g.sessionId === sessionId);
  if (!myGroup) return false;

  const members = new Set([sessionId, ...myGroup.nearbySessionIds]);
  // Only lock if there are other players nearby
  if (members.size < 2) return false;

  lockedGroups.set(sessionId, members);
  return true;
}

/**
 * Unlock a bubble group. Any member can unlock.
 */
export function unlockBubble(sessionId: string): boolean {
  // Check if this session is the owner
  if (lockedGroups.has(sessionId)) {
    lockedGroups.delete(sessionId);
    return true;
  }
  // Check if they're a member — find and remove the group
  for (const [owner, group] of lockedGroups.entries()) {
    if (group.has(sessionId)) {
      lockedGroups.delete(owner);
      return true;
    }
  }
  return false;
}

/**
 * Remove a player from all locked groups (on disconnect).
 */
export function removeFromLockedGroups(sessionId: string): void {
  // Remove groups they own
  lockedGroups.delete(sessionId);
  // Remove them from groups they're members of
  for (const [owner, group] of lockedGroups.entries()) {
    group.delete(sessionId);
    // Dissolve group if only one member left
    if (group.size < 2) {
      lockedGroups.delete(owner);
    }
  }
}

/** Check if a player is in a locked bubble. */
export function isInLockedBubble(sessionId: string): boolean {
  return findLockedGroup(sessionId) !== null;
}

/**
 * Calculate proximity groups for all connected players.
 * Respects locked bubble groups — locked members only see each other.
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
    const myLockedGroup = findLockedGroup(player.sessionId);

    if (myLockedGroup) {
      // In a locked group — only see other locked group members
      const nearbyInGroup = [...myLockedGroup].filter(
        (sid) => sid !== player.sessionId,
      );
      groups.push({
        sessionId: player.sessionId,
        nearbySessionIds: nearbyInGroup.slice(0, MAX_PEERS),
      });
      continue;
    }

    // Not in a locked group — normal proximity, but exclude locked players
    const nearby: string[] = [];
    for (const other of players) {
      if (other.sessionId === player.sessionId) continue;
      // Skip players who are in a locked group (they can't be joined)
      if (findLockedGroup(other.sessionId)) continue;
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

    // Inject megaphone speaker into all players' nearby lists
    const megaSpeaker = getMegaphoneSpeaker(state);
    if (megaSpeaker) {
      for (const group of groups) {
        if (group.sessionId !== megaSpeaker && !group.nearbySessionIds.includes(megaSpeaker)) {
          group.nearbySessionIds.push(megaSpeaker);
        }
      }
    }

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
