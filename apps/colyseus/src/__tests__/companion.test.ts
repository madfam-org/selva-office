import { describe, it, expect, vi } from "vitest";
import { handleCompanion } from "../handlers/companion";
import { OfficeStateSchema, TacticianSchema } from "../schema/OfficeState";

function createState(): OfficeStateSchema {
  const state = new OfficeStateSchema();
  const player = new TacticianSchema();
  player.sessionId = "test-session";
  player.name = "Test";
  state.players.set("test-session", player);
  return state;
}

function mockClient(sessionId = "test-session") {
  return {
    sessionId,
    send: vi.fn(),
  } as any;
}

describe("companion handler", () => {
  it("sets valid companion type", () => {
    const state = createState();
    handleCompanion(state, mockClient(), { type: "cat" });
    expect(state.players.get("test-session")?.companionType).toBe("cat");
  });

  it("rejects invalid companion type", () => {
    const state = createState();
    const client = mockClient();
    handleCompanion(state, client, { type: "unicorn" });
    expect(client.send).toHaveBeenCalledWith("error", expect.any(Object));
    expect(state.players.get("test-session")?.companionType).toBe("");
  });

  it("clears companion with empty string", () => {
    const state = createState();
    handleCompanion(state, mockClient(), { type: "dog" });
    handleCompanion(state, mockClient(), { type: "" });
    expect(state.players.get("test-session")?.companionType).toBe("");
  });

  it("accepts all valid types", () => {
    const state = createState();
    for (const type of ["cat", "dog", "robot", "dragon", "parrot", ""] as const) {
      handleCompanion(state, mockClient(), { type });
      expect(state.players.get("test-session")?.companionType).toBe(type);
    }
  });

  it("ignores unknown session", () => {
    const state = createState();
    const client = mockClient("unknown");
    handleCompanion(state, client, { type: "cat" });
    expect(state.players.get("test-session")?.companionType).toBe("");
  });
});
