import type { Client } from "@colyseus/core";
import type { OfficeStateSchema } from "../schema/OfficeState";

/**
 * Valid player status values. Players can set their own presence status
 * to signal availability to other users in the office.
 */
export const PLAYER_STATUSES = [
  "online",
  "away",
  "busy",
  "dnd",
] as const;

export type PlayerStatus = (typeof PLAYER_STATUSES)[number];

interface StatusMessage {
  status: string;
}

/**
 * Handle an incoming "status" message from a client.
 *
 * Status is persisted in the player's TacticianSchema so it is
 * automatically replicated to all connected clients via Colyseus
 * state synchronization.
 */
export function handleStatus(
  state: OfficeStateSchema,
  client: Client,
  data: StatusMessage,
): void {
  const status = typeof data.status === "string" ? data.status : "";

  // Validate against whitelist
  if (!PLAYER_STATUSES.includes(status as PlayerStatus)) {
    client.send("error", { message: `Invalid status: ${status}` });
    return;
  }

  // Check the player exists
  const player = state.players.get(client.sessionId);
  if (!player) return;

  player.playerStatus = status;
}
