import { Client } from "@colyseus/core";
import { OfficeStateSchema, ChatMessageSchema } from "../schema/OfficeState";

const MAX_CONTENT_LENGTH = 500;
const MAX_MESSAGES = 50;

const NEXUS_API_URL = process.env.NEXUS_API_URL || "http://localhost:4300";

interface ChatData {
  content: string;
}

let messageCounter = 0;

function generateMessageId(): string {
  return `msg-${Date.now()}-${++messageCounter}`;
}

/**
 * Fetch with retry: retries on network errors and 5xx responses.
 * Returns the response on success (< 500), or null after exhausting retries.
 */
async function fetchWithRetry(
  url: string,
  options: RequestInit,
  retries = 2,
  delays = [500, 1000],
): Promise<Response | null> {
  for (let i = 0; i < retries; i++) {
    try {
      const resp = await fetch(url, options);
      if (resp.ok || resp.status < 500) return resp;
    } catch {
      // network error, retry
    }
    if (i < retries - 1 && delays[i]) {
      await new Promise((r) => setTimeout(r, delays[i]));
    }
  }
  return null;
}

/**
 * Fire-and-forget POST to nexus-api to persist a chat message.
 * Follows the same pattern as task_status.py — failures are logged, never raised.
 * Retries once on network errors or 5xx responses.
 */
function persistMessage(
  roomId: string,
  senderSessionId: string,
  senderName: string,
  content: string,
  isSystem: boolean
): void {
  fetchWithRetry(`${NEXUS_API_URL}/api/v1/chat/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      room_id: roomId,
      sender_session_id: senderSessionId,
      sender_name: senderName,
      content,
      is_system: isSystem,
    }),
  }).catch((err) => {
    console.warn("Failed to persist chat message:", err.message);
  });
}

export function handleChat(
  state: OfficeStateSchema,
  client: Client,
  data: ChatData,
  roomId: string = "office"
): void {
  const content = typeof data.content === "string" ? data.content.trim() : "";

  if (content.length === 0) {
    client.send("error", {
      type: "invalid_chat",
      message: "Message content cannot be empty",
    });
    return;
  }

  if (content.length > MAX_CONTENT_LENGTH) {
    client.send("error", {
      type: "invalid_chat",
      message: `Message exceeds ${MAX_CONTENT_LENGTH} character limit`,
    });
    return;
  }

  const player = state.players.get(client.sessionId);
  const senderName = player?.name ?? "Unknown";

  const msg = new ChatMessageSchema();
  msg.id = generateMessageId();
  msg.senderSessionId = client.sessionId;
  msg.senderName = senderName;
  msg.content = content;
  msg.timestamp = Date.now();
  msg.isSystem = false;

  state.chatMessages.push(msg);

  // Trim to last MAX_MESSAGES
  while (state.chatMessages.length > MAX_MESSAGES) {
    state.chatMessages.deleteAt(0);
  }

  // Fire-and-forget persistence
  persistMessage(roomId, client.sessionId, senderName, content, false);
}

export function addSystemMessage(
  state: OfficeStateSchema,
  content: string,
  roomId: string = "office"
): void {
  const msg = new ChatMessageSchema();
  msg.id = generateMessageId();
  msg.senderSessionId = "";
  msg.senderName = "System";
  msg.content = content;
  msg.timestamp = Date.now();
  msg.isSystem = true;

  state.chatMessages.push(msg);

  while (state.chatMessages.length > MAX_MESSAGES) {
    state.chatMessages.deleteAt(0);
  }

  // Fire-and-forget persistence
  persistMessage(roomId, "", "System", content, true);
}
