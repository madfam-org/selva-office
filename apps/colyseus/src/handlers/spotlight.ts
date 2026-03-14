import type { Client } from "@colyseus/core";
import type { OfficeStateSchema } from "../schema/OfficeState";

/**
 * Spotlight handler: allows one player at a time to present their screen
 * to the entire room. First-come-first-served, following the megaphone pattern.
 * The presenter's video stream is displayed in a large view for all audience members.
 */

let currentPresenter: string | null = null;

export function getSpotlightPresenter(): string | null {
  return currentPresenter;
}

export function handleSpotlightStart(
  state: OfficeStateSchema,
  client: Client,
  broadcast: (type: string, payload: unknown) => void,
): void {
  if (currentPresenter) {
    client.send("error", { message: "Spotlight already in use" });
    return;
  }

  const player = state.players.get(client.sessionId);
  if (!player) return;

  currentPresenter = client.sessionId;
  state.spotlightPresenter = client.sessionId;
  broadcast("spotlight_active", {
    sessionId: client.sessionId,
    name: player.name,
    active: true,
  });
}

export function handleSpotlightStop(
  client: Client,
  state: OfficeStateSchema,
  broadcast: (type: string, payload: unknown) => void,
): void {
  if (currentPresenter !== client.sessionId) {
    client.send("error", { message: "You are not the spotlight presenter" });
    return;
  }

  currentPresenter = null;
  state.spotlightPresenter = "";
  broadcast("spotlight_active", {
    sessionId: client.sessionId,
    active: false,
  });
}

/** Release spotlight if the presenter disconnects. */
export function releaseSpotlight(
  sessionId: string,
  state: OfficeStateSchema,
  broadcast: (type: string, payload: unknown) => void,
): void {
  if (currentPresenter === sessionId) {
    currentPresenter = null;
    state.spotlightPresenter = "";
    broadcast("spotlight_active", {
      sessionId,
      active: false,
    });
  }
}
