import type { Client } from "@colyseus/core";
import { MapSchema } from "@colyseus/schema";
import { WhiteboardSchema, StrokeSchema } from "../schema/Whiteboard";

/**
 * Maximum number of strokes per whiteboard. When exceeded, the oldest
 * strokes are removed (ring buffer behaviour).
 */
export const MAX_STROKES = 5000;

/** Allowed tool values for validation. */
const VALID_TOOLS = ["pen", "eraser"] as const;

/** Hex colour pattern: # followed by 3 or 6 hex digits. */
const HEX_COLOR_RE = /^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/;

export interface DrawStrokeMessage {
  whiteboardId?: string;
  x: number;
  y: number;
  toX: number;
  toY: number;
  color?: string;
  width?: number;
  tool?: string;
}

export interface ClearWhiteboardMessage {
  whiteboardId?: string;
}

function isFiniteNumber(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v);
}

/**
 * Handle a `draw_stroke` message from a client.
 * Validates fields, creates a StrokeSchema, and appends it to the
 * whiteboard's strokes array. Trims oldest strokes when > MAX_STROKES.
 */
export function handleWhiteboardDraw(
  whiteboards: MapSchema<WhiteboardSchema>,
  client: Client,
  data: DrawStrokeMessage,
): void {
  // Validate coordinate fields
  if (
    !isFiniteNumber(data.x) ||
    !isFiniteNumber(data.y) ||
    !isFiniteNumber(data.toX) ||
    !isFiniteNumber(data.toY)
  ) {
    client.send("error", { message: "Invalid stroke coordinates" });
    return;
  }

  // Validate optional colour
  const color =
    typeof data.color === "string" && HEX_COLOR_RE.test(data.color)
      ? data.color
      : "#ffffff";

  // Validate optional width (clamp to 1-20)
  const width = isFiniteNumber(data.width)
    ? Math.max(1, Math.min(20, Math.round(data.width)))
    : 2;

  // Validate optional tool
  const tool =
    typeof data.tool === "string" &&
    (VALID_TOOLS as readonly string[]).includes(data.tool)
      ? data.tool
      : "pen";

  const whiteboardId =
    typeof data.whiteboardId === "string" && data.whiteboardId
      ? data.whiteboardId
      : "main";

  // Get or create whiteboard
  let wb = whiteboards.get(whiteboardId);
  if (!wb) {
    wb = new WhiteboardSchema();
    wb.id = whiteboardId;
    whiteboards.set(whiteboardId, wb);
  }

  // Create stroke
  const stroke = new StrokeSchema();
  stroke.x = data.x;
  stroke.y = data.y;
  stroke.toX = data.toX;
  stroke.toY = data.toY;
  stroke.color = color;
  stroke.width = width;
  stroke.tool = tool;
  stroke.senderId = client.sessionId;

  wb.strokes.push(stroke);

  // Ring buffer: trim oldest strokes
  while (wb.strokes.length > MAX_STROKES) {
    wb.strokes.shift();
  }
}

/**
 * Handle a `clear_whiteboard` message from a client.
 * Removes all strokes from the specified whiteboard.
 */
export function handleWhiteboardClear(
  whiteboards: MapSchema<WhiteboardSchema>,
  client: Client,
  data: ClearWhiteboardMessage,
): void {
  const whiteboardId =
    typeof data.whiteboardId === "string" && data.whiteboardId
      ? data.whiteboardId
      : "main";

  const wb = whiteboards.get(whiteboardId);
  if (!wb) {
    client.send("error", { message: `Whiteboard not found: ${whiteboardId}` });
    return;
  }

  wb.strokes.clear();
}
