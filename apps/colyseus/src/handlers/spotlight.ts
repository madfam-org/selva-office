import type { Client } from "@colyseus/core";
import type { OfficeStateSchema } from "../schema/OfficeState";

/**
 * Spotlight handler: allows one player at a time to present their screen
 * to the entire room. First-come-first-served, following the megaphone pattern.
 * The presenter's video stream is displayed in a large view for all audience members.
 */

export function getSpotlightPresenter(state: OfficeStateSchema): string | null {
  return state.spotlightPresenter || null;
}

export function handleSpotlightStart(
  state: OfficeStateSchema,
  client: Client,
  broadcast: (type: string, payload: unknown) => void,
): void {
  if (state.spotlightPresenter) {
    client.send("error", { message: "Spotlight already in use" });
    return;
  }

  const player = state.players.get(client.sessionId);
  if (!player) {
    client.send("error", { message: "Player not found" });
    return;
  }

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
  if (state.spotlightPresenter !== client.sessionId) {
    client.send("error", { message: "You are not the spotlight presenter" });
    return;
  }

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
  if (state.spotlightPresenter === sessionId) {
    state.spotlightPresenter = "";
    broadcast("spotlight_active", {
      sessionId,
      active: false,
    });
  }
}
