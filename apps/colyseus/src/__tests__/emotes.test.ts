import { describe, it, expect, vi } from "vitest";
import { OfficeStateSchema, TacticianSchema } from "../schema/OfficeState";
import { handleEmote, EMOTE_TYPES } from "../handlers/emotes";

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

describe("handleEmote", () => {
  it("broadcasts valid emote to all clients", () => {
    const state = createStateWithPlayer("abc", "Alice");
    const client = createMockClient("abc");
    const broadcast = vi.fn();

    handleEmote(state, client, { type: "wave" }, broadcast);

    expect(broadcast).toHaveBeenCalledWith("player_emote", {
      sessionId: "abc",
      emoteType: "wave",
      playerName: "Alice",
    });
  });

  it("rejects invalid emote types", () => {
    const state = createStateWithPlayer("abc", "Alice");
    const client = createMockClient("abc");
    const broadcast = vi.fn();

    handleEmote(state, client, { type: "invalid_emote" }, broadcast);

    expect(broadcast).not.toHaveBeenCalled();
    expect(client.send).toHaveBeenCalledWith("error", {
      message: "Invalid emote type: invalid_emote",
    });
  });

  it("rejects empty emote type", () => {
    const state = createStateWithPlayer("abc", "Alice");
    const client = createMockClient("abc");
    const broadcast = vi.fn();

    handleEmote(state, client, { type: "" }, broadcast);

    expect(broadcast).not.toHaveBeenCalled();
  });

  it("rejects non-string emote type", () => {
    const state = createStateWithPlayer("abc", "Alice");
    const client = createMockClient("abc");
    const broadcast = vi.fn();

    handleEmote(state, client, { type: 123 as any }, broadcast);

    expect(broadcast).not.toHaveBeenCalled();
  });

  it("does nothing for unknown session", () => {
    const state = new OfficeStateSchema();
    const client = createMockClient("unknown");
    const broadcast = vi.fn();

    handleEmote(state, client, { type: "wave" }, broadcast);

    expect(broadcast).not.toHaveBeenCalled();
  });

  it("accepts all valid emote types", () => {
    const state = createStateWithPlayer("abc", "Alice");
    const client = createMockClient("abc");
    const broadcast = vi.fn();

    for (const emoteType of EMOTE_TYPES) {
      handleEmote(state, client, { type: emoteType }, broadcast);
    }

    expect(broadcast).toHaveBeenCalledTimes(EMOTE_TYPES.length);
  });

  it("includes player name in broadcast", () => {
    const state = createStateWithPlayer("xyz", "Bob");
    const client = createMockClient("xyz");
    const broadcast = vi.fn();

    handleEmote(state, client, { type: "heart" }, broadcast);

    expect(broadcast).toHaveBeenCalledWith("player_emote", {
      sessionId: "xyz",
      emoteType: "heart",
      playerName: "Bob",
    });
  });
});
