import { describe, it, expect, vi, beforeEach } from "vitest";
import { MapSchema } from "@colyseus/schema";
import {
  handleWhiteboardDraw,
  handleWhiteboardClear,
  MAX_STROKES,
} from "../handlers/whiteboard";
import { WhiteboardSchema, StrokeSchema } from "../schema/Whiteboard";

function createWhiteboards(): MapSchema<WhiteboardSchema> {
  const whiteboards = new MapSchema<WhiteboardSchema>();
  const main = new WhiteboardSchema();
  main.id = "main";
  whiteboards.set("main", main);
  return whiteboards;
}

function mockClient(sessionId = "test-session") {
  return {
    sessionId,
    send: vi.fn(),
  } as any;
}

describe("whiteboard handler", () => {
  let whiteboards: MapSchema<WhiteboardSchema>;

  beforeEach(() => {
    whiteboards = createWhiteboards();
  });

  it("creates a stroke with valid data", () => {
    const client = mockClient();
    handleWhiteboardDraw(whiteboards, client, {
      x: 10,
      y: 20,
      toX: 30,
      toY: 40,
      color: "#ff0000",
      width: 3,
      tool: "pen",
    });

    const wb = whiteboards.get("main")!;
    expect(wb.strokes.length).toBe(1);
    const s = wb.strokes.at(0)!;
    expect(s.x).toBe(10);
    expect(s.y).toBe(20);
    expect(s.toX).toBe(30);
    expect(s.toY).toBe(40);
    expect(s.color).toBe("#ff0000");
    expect(s.width).toBe(3);
    expect(s.tool).toBe("pen");
    expect(s.senderId).toBe("test-session");
  });

  it("rejects invalid coordinates", () => {
    const client = mockClient();
    handleWhiteboardDraw(whiteboards, client, {
      x: NaN,
      y: 20,
      toX: 30,
      toY: 40,
    });

    const wb = whiteboards.get("main")!;
    expect(wb.strokes.length).toBe(0);
    expect(client.send).toHaveBeenCalledWith("error", expect.any(Object));
  });

  it("enforces max strokes ring buffer", () => {
    const client = mockClient();
    const wb = whiteboards.get("main")!;

    // Fill to MAX_STROKES + 3
    for (let i = 0; i < MAX_STROKES + 3; i++) {
      handleWhiteboardDraw(whiteboards, client, {
        x: i,
        y: 0,
        toX: i + 1,
        toY: 1,
      });
    }

    expect(wb.strokes.length).toBe(MAX_STROKES);
    // The oldest strokes should have been shifted out; the first one should be x=3
    expect(wb.strokes.at(0)!.x).toBe(3);
  });

  it("clears whiteboard", () => {
    const client = mockClient();
    handleWhiteboardDraw(whiteboards, client, {
      x: 0,
      y: 0,
      toX: 10,
      toY: 10,
    });
    expect(whiteboards.get("main")!.strokes.length).toBe(1);

    handleWhiteboardClear(whiteboards, client, {});
    expect(whiteboards.get("main")!.strokes.length).toBe(0);
  });

  it("has correct stroke schema defaults", () => {
    const s = new StrokeSchema();
    expect(s.x).toBe(0);
    expect(s.y).toBe(0);
    expect(s.toX).toBe(0);
    expect(s.toY).toBe(0);
    expect(s.color).toBe("#ffffff");
    expect(s.width).toBe(2);
    expect(s.tool).toBe("pen");
    expect(s.senderId).toBe("");
  });

  it("creates default whiteboard on init", () => {
    expect(whiteboards.get("main")).toBeDefined();
    expect(whiteboards.get("main")!.id).toBe("main");
    expect(whiteboards.get("main")!.strokes.length).toBe(0);
  });

  it("uses default color and tool when invalid values provided", () => {
    const client = mockClient();
    handleWhiteboardDraw(whiteboards, client, {
      x: 0,
      y: 0,
      toX: 10,
      toY: 10,
      color: "not-a-color",
      tool: "spray-can",
    });

    const s = whiteboards.get("main")!.strokes.at(0)!;
    expect(s.color).toBe("#ffffff");
    expect(s.tool).toBe("pen");
  });

  it("clamps width to valid range", () => {
    const client = mockClient();
    handleWhiteboardDraw(whiteboards, client, {
      x: 0,
      y: 0,
      toX: 10,
      toY: 10,
      width: 50,
    });
    expect(whiteboards.get("main")!.strokes.at(0)!.width).toBe(20);

    handleWhiteboardDraw(whiteboards, client, {
      x: 0,
      y: 0,
      toX: 10,
      toY: 10,
      width: -5,
    });
    expect(whiteboards.get("main")!.strokes.at(1)!.width).toBe(1);
  });

  it("sends error on clear of non-existent whiteboard", () => {
    const client = mockClient();
    handleWhiteboardClear(whiteboards, client, {
      whiteboardId: "nonexistent",
    });
    expect(client.send).toHaveBeenCalledWith(
      "error",
      expect.objectContaining({ message: expect.stringContaining("nonexistent") }),
    );
  });

  it("auto-creates whiteboard if it does not exist on draw", () => {
    const client = mockClient();
    handleWhiteboardDraw(whiteboards, client, {
      whiteboardId: "new-board",
      x: 0,
      y: 0,
      toX: 10,
      toY: 10,
    });

    const wb = whiteboards.get("new-board");
    expect(wb).toBeDefined();
    expect(wb!.id).toBe("new-board");
    expect(wb!.strokes.length).toBe(1);
  });
});
