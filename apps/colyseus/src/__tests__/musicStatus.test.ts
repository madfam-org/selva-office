import { describe, it, expect, vi } from "vitest";
import { OfficeStateSchema, TacticianSchema } from "../schema/OfficeState";
import { handleMusicStatus } from "../handlers/status";

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

describe("handleMusicStatus", () => {
  it("sets music status on the player", () => {
    const state = createStateWithPlayer("abc", "Alice");
    const client = createMockClient("abc");

    handleMusicStatus(state, client, { status: "\u{1F3B5} Working" });

    expect(state.players.get("abc")!.musicStatus).toBe("\u{1F3B5} Working");
  });

  it("rejects music status longer than 50 chars", () => {
    const state = createStateWithPlayer("abc", "Alice");
    const client = createMockClient("abc");
    const longStatus = "a".repeat(51);

    handleMusicStatus(state, client, { status: longStatus });

    expect(state.players.get("abc")!.musicStatus).toBe("");
    expect(client.send).toHaveBeenCalledWith("error", {
      message: "Music status too long (max 50 chars)",
    });
  });

  it("clears music status with empty string", () => {
    const state = createStateWithPlayer("abc", "Alice");
    const client = createMockClient("abc");

    handleMusicStatus(state, client, { status: "\u{1F3A7} Coding" });
    expect(state.players.get("abc")!.musicStatus).toBe("\u{1F3A7} Coding");

    handleMusicStatus(state, client, { status: "" });
    expect(state.players.get("abc")!.musicStatus).toBe("");
  });

  it("accepts exactly 50 chars", () => {
    const state = createStateWithPlayer("abc", "Alice");
    const client = createMockClient("abc");
    const maxStatus = "a".repeat(50);

    handleMusicStatus(state, client, { status: maxStatus });

    expect(state.players.get("abc")!.musicStatus).toBe(maxStatus);
    expect(client.send).not.toHaveBeenCalled();
  });

  it("handles non-string data gracefully", () => {
    const state = createStateWithPlayer("abc", "Alice");
    const client = createMockClient("abc");

    handleMusicStatus(state, client, { status: 123 as any });

    // Non-string coerced to empty string
    expect(state.players.get("abc")!.musicStatus).toBe("");
  });

  it("does nothing for unknown session", () => {
    const state = new OfficeStateSchema();
    const client = createMockClient("unknown");

    handleMusicStatus(state, client, { status: "test" });

    expect(client.send).toHaveBeenCalledWith("error", { message: "Player not found" });
  });
});
