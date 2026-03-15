import type { Client } from "@colyseus/core";
import type { OfficeStateSchema } from "../schema/OfficeState";

/**
 * Teleport offset to avoid overlapping with the target player.
 */
const TELEPORT_OFFSET = 40;

interface TeleportMessage {
  targetSessionId: string;
}

/**
 * Handle an incoming "teleport" message — move the requesting player
 * to the position of the target player with a small offset.
 */
export function handleTeleport(
  state: OfficeStateSchema,
  client: Client,
  data: TeleportMessage
): void {
  const targetId =
    typeof data.targetSessionId === "string" ? data.targetSessionId : "";

  if (!targetId) {
    client.send("error", {
      type: "invalid_teleport",
      message: "targetSessionId is required",
    });
    return;
  }

  const target = state.players.get(targetId);
  if (!target) {
    client.send("error", {
      type: "invalid_teleport",
      message: "Target player not found",
    });
    return;
  }

  const player = state.players.get(client.sessionId);
  if (!player) return;

  // Teleport with offset to avoid sitting on top of the target
  player.x = target.x + TELEPORT_OFFSET;
  player.y = target.y;
}
