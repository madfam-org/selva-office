import type { Client } from "@colyseus/core";
import type { OfficeStateSchema } from "../schema/OfficeState";

interface AvatarMessage {
  config: string;
}

interface AvatarConfigData {
  skinTone: number;
  hairStyle: number;
  hairColor: number;
  outfitColor: number;
  accessory: number;
}

const VALID_RANGES: Record<keyof AvatarConfigData, [number, number]> = {
  skinTone: [0, 3],
  hairStyle: [-1, 3],
  hairColor: [0, 3],
  outfitColor: [0, 3],
  accessory: [-1, 4],
};

function isValidConfig(data: unknown): data is AvatarConfigData {
  if (typeof data !== "object" || data === null) return false;
  const obj = data as Record<string, unknown>;

  for (const [key, [min, max]] of Object.entries(VALID_RANGES)) {
    const val = obj[key];
    if (typeof val !== "number" || !Number.isInteger(val)) return false;
    if (val < min || val > max) return false;
  }
  return true;
}

/**
 * Handle an incoming "avatar" message from a client.
 * Validates the avatar configuration and stores it on the player schema.
 */
export function handleAvatar(
  state: OfficeStateSchema,
  client: Client,
  data: AvatarMessage,
): void {
  const player = state.players.get(client.sessionId);
  if (!player) return;

  let parsed: unknown;
  try {
    parsed = JSON.parse(data.config);
  } catch {
    client.send("error", { message: "Invalid avatar config JSON" });
    return;
  }

  if (!isValidConfig(parsed)) {
    client.send("error", { message: "Avatar config values out of range" });
    return;
  }

  player.avatarConfig = data.config;
}
