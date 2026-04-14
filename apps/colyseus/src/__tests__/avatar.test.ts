import { describe, it, expect, vi } from "vitest";
import { OfficeStateSchema, TacticianSchema } from "../schema/OfficeState";
import { handleAvatar } from "../handlers/avatar";

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
  state.players.set(sessionId, player);
  return state;
}

describe("handleAvatar", () => {
  it("stores valid avatar config on the player", () => {
    const state = createStateWithPlayer("abc", "Alice");
    const client = createMockClient("abc");
    const config = JSON.stringify({
      skinTone: 2,
      hairStyle: 1,
      hairColor: 3,
      outfitColor: 0,
      accessory: 1,
    });

    handleAvatar(state, client, { config });

    expect(state.players.get("abc")!.avatarConfig).toBe(config);
  });

  it("rejects invalid JSON", () => {
    const state = createStateWithPlayer("abc", "Alice");
    const client = createMockClient("abc");

    handleAvatar(state, client, { config: "not json" });

    expect(state.players.get("abc")!.avatarConfig).toBe("");
    expect(client.send).toHaveBeenCalledWith("error", {
      message: "Invalid avatar config JSON",
    });
  });

  it("rejects out-of-range values", () => {
    const state = createStateWithPlayer("abc", "Alice");
    const client = createMockClient("abc");
    const config = JSON.stringify({
      skinTone: 99,
      hairStyle: 0,
      hairColor: 0,
      outfitColor: 0,
      accessory: 0,
    });

    handleAvatar(state, client, { config });

    expect(state.players.get("abc")!.avatarConfig).toBe("");
    expect(client.send).toHaveBeenCalledWith("error", {
      message: "Avatar config values out of range",
    });
  });

  it("does nothing for unknown session", () => {
    const state = new OfficeStateSchema();
    const client = createMockClient("unknown");

    handleAvatar(state, client, {
      config: JSON.stringify({
        skinTone: 0,
        hairStyle: 0,
        hairColor: 0,
        outfitColor: 0,
        accessory: -1,
      }),
    });

    expect(client.send).toHaveBeenCalledWith("error", { message: "Player not found" });
  });

  it("accepts hair style -1 (bald) and accessory -1 (none)", () => {
    const state = createStateWithPlayer("abc", "Alice");
    const client = createMockClient("abc");
    const config = JSON.stringify({
      skinTone: 0,
      hairStyle: -1,
      hairColor: 0,
      outfitColor: 0,
      accessory: -1,
    });

    handleAvatar(state, client, { config });

    expect(state.players.get("abc")!.avatarConfig).toBe(config);
  });

  it("rejects non-integer values", () => {
    const state = createStateWithPlayer("abc", "Alice");
    const client = createMockClient("abc");
    const config = JSON.stringify({
      skinTone: 1.5,
      hairStyle: 0,
      hairColor: 0,
      outfitColor: 0,
      accessory: 0,
    });

    handleAvatar(state, client, { config });

    expect(state.players.get("abc")!.avatarConfig).toBe("");
  });

  it("rejects missing fields", () => {
    const state = createStateWithPlayer("abc", "Alice");
    const client = createMockClient("abc");
    const config = JSON.stringify({ skinTone: 0 });

    handleAvatar(state, client, { config });

    expect(state.players.get("abc")!.avatarConfig).toBe("");
  });
});
