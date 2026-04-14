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
  if (!player) {
    client.send("error", { message: "Player not found" });
    return;
  }

  player.playerStatus = status;
}

interface MusicStatusMessage {
  status: string;
}

/**
 * Handle an incoming "music_status" message from a client.
 *
 * Music status is a free-text field (max 50 chars) allowing players
 * to share what they are listening to or their current mood.
 */
export function handleMusicStatus(
  state: OfficeStateSchema,
  client: Client,
  data: MusicStatusMessage,
): void {
  const status = typeof data.status === "string" ? data.status : "";

  if (status.length > 50) {
    client.send("error", { message: "Music status too long (max 50 chars)" });
    return;
  }

  const player = state.players.get(client.sessionId);
  if (!player) {
    client.send("error", { message: "Player not found" });
    return;
  }

  player.musicStatus = status;
}

interface MeetingTitleMessage {
  title: string;
}

/**
 * Handle an incoming "meeting_title" message from a client.
 *
 * Meeting title is set by the calendar integration to show the current
 * meeting name on the player's avatar. Max 100 chars.
 */
export function handleMeetingTitle(
  state: OfficeStateSchema,
  client: Client,
  data: MeetingTitleMessage,
): void {
  const title = typeof data.title === "string" ? data.title : "";

  if (title.length > 100) {
    client.send("error", { message: "Meeting title too long (max 100 chars)" });
    return;
  }

  const player = state.players.get(client.sessionId);
  if (!player) {
    client.send("error", { message: "Player not found" });
    return;
  }

  player.meetingTitle = title;
}
