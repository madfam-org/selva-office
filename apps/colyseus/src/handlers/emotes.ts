import type { Client } from "@colyseus/core";
import type { OfficeStateSchema } from "../schema/OfficeState";

/**
 * Valid emote types. The client sends one of these strings;
 * the server validates against this whitelist before broadcasting.
 */
export const EMOTE_TYPES = [
  "wave",
  "thumbsup",
  "heart",
  "laugh",
  "think",
  "clap",
  "fire",
  "sparkle",
  "coffee",
] as const;

export type EmoteType = (typeof EMOTE_TYPES)[number];

interface EmoteMessage {
  type: string;
}

/**
 * Handle an incoming "emote" message from a client.
 *
 * Emotes are ephemeral — they are NOT persisted in the schema.
 * Instead, the room broadcasts a `player_emote` message to all
 * clients, which render the emote bubble locally.
 */
export function handleEmote(
  state: OfficeStateSchema,
  client: Client,
  data: EmoteMessage,
  broadcast: (type: string, message: unknown) => void,
): void {
  const emoteType = typeof data.type === "string" ? data.type : "";

  // Validate against whitelist
  if (!EMOTE_TYPES.includes(emoteType as EmoteType)) {
    client.send("error", { message: `Invalid emote type: ${emoteType}` });
    return;
  }

  // Check the player exists
  const player = state.players.get(client.sessionId);
  if (!player) {
    client.send("error", { message: "Player not found" });
    return;
  }

  // Broadcast to all clients (including sender, so they see it too)
  broadcast("player_emote", {
    sessionId: client.sessionId,
    emoteType,
    playerName: player.name,
  });
}
