import type { Client } from "@colyseus/core";
import type { OfficeStateSchema } from "../schema/OfficeState";

/**
 * Megaphone handler: allows one player at a time to broadcast audio to all.
 * First-come-first-served. The speaker's audio is injected into ALL players'
 * proximity groups via the `megaphone_active` broadcast.
 */

export function getMegaphoneSpeaker(state: OfficeStateSchema): string | null {
  return state.megaphoneSpeaker || null;
}

export function handleMegaphoneStart(
  state: OfficeStateSchema,
  client: Client,
  broadcast: (type: string, payload: unknown) => void,
): void {
  if (state.megaphoneSpeaker) {
    client.send("error", {
      message: `Megaphone in use by another player`,
    });
    return;
  }

  const player = state.players.get(client.sessionId);
  if (!player) {
    client.send("error", { message: "Player not found" });
    return;
  }

  state.megaphoneSpeaker = client.sessionId;
  broadcast("megaphone_active", {
    sessionId: client.sessionId,
    name: player.name,
    active: true,
  });
}

export function handleMegaphoneStop(
  state: OfficeStateSchema,
  client: Client,
  broadcast: (type: string, payload: unknown) => void,
): void {
  if (state.megaphoneSpeaker !== client.sessionId) {
    client.send("error", { message: "You are not the megaphone speaker" });
    return;
  }

  state.megaphoneSpeaker = "";
  broadcast("megaphone_active", {
    sessionId: client.sessionId,
    active: false,
  });
}

/** Release megaphone if the speaker disconnects. */
export function releaseMegaphone(
  sessionId: string,
  state: OfficeStateSchema,
  broadcast: (type: string, payload: unknown) => void,
): void {
  if (state.megaphoneSpeaker === sessionId) {
    state.megaphoneSpeaker = "";
    broadcast("megaphone_active", {
      sessionId,
      active: false,
    });
  }
}
