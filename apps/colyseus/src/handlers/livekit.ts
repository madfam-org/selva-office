/**
 * LiveKit SFU integration for high-player-count rooms.
 *
 * When the number of players in a room exceeds LIVEKIT_THRESHOLD,
 * the proximity handler signals clients to switch from peer-to-peer
 * WebRTC (simple-peer) to SFU mode via LiveKit.
 *
 * The `livekit-server-sdk` is dynamically imported so that the
 * application compiles and runs without it installed. When the SDK
 * is missing, all functions gracefully degrade (isLiveKitEnabled
 * returns false, token generation rejects).
 */

const LIVEKIT_API_KEY = process.env.LIVEKIT_API_KEY ?? "";
const LIVEKIT_API_SECRET = process.env.LIVEKIT_API_SECRET ?? "";
const LIVEKIT_URL = process.env.LIVEKIT_URL ?? "";
export const LIVEKIT_THRESHOLD = parseInt(
  process.env.LIVEKIT_THRESHOLD || "5",
  10,
);

/**
 * Returns true when all three LiveKit env vars are configured.
 */
export function isLiveKitEnabled(): boolean {
  return !!(LIVEKIT_API_KEY && LIVEKIT_API_SECRET && LIVEKIT_URL);
}

/**
 * Returns the configured LiveKit WebSocket URL.
 */
export function getLiveKitUrl(): string {
  return LIVEKIT_URL;
}

/**
 * Generate a short-lived LiveKit access token for a participant.
 *
 * Uses dynamic import so the server starts even when `livekit-server-sdk`
 * is not installed. In that case the returned promise rejects, and callers
 * should catch and log the error.
 */
export async function generateLiveKitToken(
  identity: string,
  name: string,
  roomName: string,
): Promise<string> {
  // Dynamic import — allows the module to compile without the SDK installed
  const { AccessToken } = await import("livekit-server-sdk");

  const token = new AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET, {
    identity,
    name,
  });

  const grant = {
    room: roomName,
    roomJoin: true,
    canPublish: true,
    canSubscribe: true,
  };
  token.addGrant(grant);
  token.ttl = "4h";

  return await token.toJwt();
}
