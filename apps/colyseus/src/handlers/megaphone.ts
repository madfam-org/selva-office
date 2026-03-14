import type { Client } from "@colyseus/core";
import type { OfficeStateSchema } from "../schema/OfficeState";

/**
 * Megaphone handler: allows one player at a time to broadcast audio to all.
 * First-come-first-served. The speaker's audio is injected into ALL players'
 * proximity groups via the `megaphone_active` broadcast.
 */

let currentSpeaker: string | null = null;

export function getMegaphoneSpeaker(): string | null {
  return currentSpeaker;
}

export function handleMegaphoneStart(
  state: OfficeStateSchema,
  client: Client,
  broadcast: (type: string, payload: unknown) => void,
): void {
  if (currentSpeaker) {
    client.send("error", {
      message: `Megaphone in use by another player`,
    });
    return;
  }

  const player = state.players.get(client.sessionId);
  if (!player) return;

  currentSpeaker = client.sessionId;
  broadcast("megaphone_active", {
    sessionId: client.sessionId,
    name: player.name,
    active: true,
  });
}

export function handleMegaphoneStop(
  client: Client,
  broadcast: (type: string, payload: unknown) => void,
): void {
  if (currentSpeaker !== client.sessionId) {
    client.send("error", { message: "You are not the megaphone speaker" });
    return;
  }

  currentSpeaker = null;
  broadcast("megaphone_active", {
    sessionId: client.sessionId,
    active: false,
  });
}

/** Release megaphone if the speaker disconnects. */
export function releaseMegaphone(
  sessionId: string,
  broadcast: (type: string, payload: unknown) => void,
): void {
  if (currentSpeaker === sessionId) {
    currentSpeaker = null;
    broadcast("megaphone_active", {
      sessionId,
      active: false,
    });
  }
}
