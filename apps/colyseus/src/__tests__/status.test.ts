import { describe, it, expect, vi } from "vitest";
import { OfficeStateSchema, TacticianSchema } from "../schema/OfficeState";
import { handleStatus, PLAYER_STATUSES } from "../handlers/status";

function createMockClient(sessionId: string) {
  return {
    sessionId,
    send: vi.fn(),
  } as any;
}

function createStateWithPlayer(sessionId: string, name: string) {
  const state = new OfficeStateSchema();
  const player = new TacticianSchema();
  player.sessionId = sessionId;
  player.name = name;
  player.x = 400;
  player.y = 300;
  state.players.set(sessionId, player);
  return state;
}

describe("handleStatus", () => {
  it("sets valid status on the player", () => {
    const state = createStateWithPlayer("abc", "Alice");
    const client = createMockClient("abc");

    handleStatus(state, client, { status: "busy" });

    expect(state.players.get("abc")!.playerStatus).toBe("busy");
  });

  it("rejects invalid status values", () => {
    const state = createStateWithPlayer("abc", "Alice");
    const client = createMockClient("abc");

    handleStatus(state, client, { status: "invisible" });

    expect(state.players.get("abc")!.playerStatus).toBe("online");
    expect(client.send).toHaveBeenCalledWith("error", {
      message: "Invalid status: invisible",
    });
  });

  it("rejects empty status", () => {
    const state = createStateWithPlayer("abc", "Alice");
    const client = createMockClient("abc");

    handleStatus(state, client, { status: "" });

    expect(state.players.get("abc")!.playerStatus).toBe("online");
    expect(client.send).toHaveBeenCalledWith("error", {
      message: "Invalid status: ",
    });
  });

  it("rejects non-string status", () => {
    const state = createStateWithPlayer("abc", "Alice");
    const client = createMockClient("abc");

    handleStatus(state, client, { status: 123 as any });

    expect(state.players.get("abc")!.playerStatus).toBe("online");
    expect(client.send).toHaveBeenCalledWith("error", {
      message: "Invalid status: ",
    });
  });

  it("does nothing for unknown session", () => {
    const state = new OfficeStateSchema();
    const client = createMockClient("unknown");

    handleStatus(state, client, { status: "busy" });

    expect(client.send).not.toHaveBeenCalled();
  });

  it("accepts all valid status types", () => {
    const state = createStateWithPlayer("abc", "Alice");
    const client = createMockClient("abc");

    for (const status of PLAYER_STATUSES) {
      handleStatus(state, client, { status });
      expect(state.players.get("abc")!.playerStatus).toBe(status);
    }
  });

  it("defaults to online when player is created", () => {
    const state = createStateWithPlayer("abc", "Alice");
    expect(state.players.get("abc")!.playerStatus).toBe("online");
  });
});
