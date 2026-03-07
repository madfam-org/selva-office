import type { Client } from "@colyseus/core";

export interface WebRTCSignalMessage {
  targetSessionId: string;
  signal: unknown;
}

/**
 * Relay a WebRTC signaling message from one client to another.
 * The server acts as a simple pass-through relay — it does not inspect
 * or modify the signal payload (SDP offers/answers, ICE candidates).
 */
export function handleSignaling(
  client: Client,
  message: WebRTCSignalMessage,
  getClients: () => Client[]
): void {
  if (!message.targetSessionId || !message.signal) return;

  const target = getClients().find(
    (c) => c.sessionId === message.targetSessionId
  );
  if (!target) return;

  target.send("webrtc_signal", {
    fromSessionId: client.sessionId,
    signal: message.signal,
  });
}
