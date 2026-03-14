import type { Client } from "@colyseus/core";
import type { OfficeStateSchema } from "../schema/OfficeState";

/**
 * Valid companion types. Empty string means no companion.
 */
export const COMPANION_TYPES = [
  "",
  "cat",
  "dog",
  "robot",
  "dragon",
  "parrot",
] as const;

export type CompanionType = (typeof COMPANION_TYPES)[number];

interface CompanionMessage {
  type: string;
}

/**
 * Handle an incoming "companion" message from a client.
 * Validates the companion type against a whitelist and stores
 * it on the player schema for sync to all clients.
 */
export function handleCompanion(
  state: OfficeStateSchema,
  client: Client,
  message: CompanionMessage,
): void {
  const companionType = typeof message.type === "string" ? message.type : "";

  if (!COMPANION_TYPES.includes(companionType as CompanionType)) {
    client.send("error", {
      message: `Invalid companion type: ${companionType}`,
    });
    return;
  }

  const player = state.players.get(client.sessionId);
  if (player) {
    player.companionType = companionType;
  }
}
