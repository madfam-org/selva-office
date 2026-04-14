import { describe, it, expect, beforeEach, vi } from "vitest";
import {
  handleMegaphoneStart,
  handleMegaphoneStop,
  releaseMegaphone,
  getMegaphoneSpeaker,
} from "../handlers/megaphone";
import { OfficeStateSchema, TacticianSchema } from "../schema/OfficeState";

function createState(): OfficeStateSchema {
  const state = new OfficeStateSchema();
  return state;
}

function addPlayer(state: OfficeStateSchema, sessionId: string): void {
  const player = new TacticianSchema();
  player.sessionId = sessionId;
  player.name = `Player-${sessionId}`;
  state.players.set(sessionId, player);
}

function mockClient(sessionId: string) {
  return {
    sessionId,
    send: vi.fn(),
  } as any;
}

describe("megaphone", () => {
  let resetState: OfficeStateSchema;

  beforeEach(() => {
    // Reset megaphone state via a shared state object
    resetState = createState();
    const broadcast = vi.fn();
    releaseMegaphone("a", resetState, broadcast);
    releaseMegaphone("b", resetState, broadcast);
  });

  it("allows first player to start megaphone", () => {
    const state = createState();
    addPlayer(state, "a");
    const client = mockClient("a");
    const broadcast = vi.fn();

    handleMegaphoneStart(state, client, broadcast);

    expect(getMegaphoneSpeaker(state)).toBe("a");
    expect(broadcast).toHaveBeenCalledWith("megaphone_active", {
      sessionId: "a",
      name: "Player-a",
      active: true,
    });
  });

  it("blocks second player from starting megaphone", () => {
    const state = createState();
    addPlayer(state, "a");
    addPlayer(state, "b");
    const broadcast = vi.fn();

    handleMegaphoneStart(state, mockClient("a"), broadcast);
    handleMegaphoneStart(state, mockClient("b"), broadcast);

    expect(getMegaphoneSpeaker(state)).toBe("a");
  });

  it("stops megaphone", () => {
    const state = createState();
    addPlayer(state, "a");
    const broadcast = vi.fn();

    handleMegaphoneStart(state, mockClient("a"), broadcast);
    handleMegaphoneStop(state, mockClient("a"), broadcast);

    expect(getMegaphoneSpeaker(state)).toBeNull();
    expect(broadcast).toHaveBeenLastCalledWith("megaphone_active", {
      sessionId: "a",
      active: false,
    });
  });

  it("rejects stop from non-speaker", () => {
    const state = createState();
    addPlayer(state, "a");
    const clientB = mockClient("b");
    const broadcast = vi.fn();

    handleMegaphoneStart(state, mockClient("a"), broadcast);
    handleMegaphoneStop(state, clientB, broadcast);

    expect(getMegaphoneSpeaker(state)).toBe("a");
    expect(clientB.send).toHaveBeenCalledWith("error", expect.any(Object));
  });

  it("releases megaphone on disconnect", () => {
    const state = createState();
    addPlayer(state, "a");
    const broadcast = vi.fn();

    handleMegaphoneStart(state, mockClient("a"), broadcast);
    releaseMegaphone("a", state, broadcast);

    expect(getMegaphoneSpeaker(state)).toBeNull();
  });

  it("has megaphoneSpeaker field on schema with correct default", () => {
    const state = createState();
    expect(state.megaphoneSpeaker).toBe("");
  });

  it("sends error when player not found", () => {
    const state = createState();
    // Do not add player — state has no players
    const client = mockClient("unknown");
    const broadcast = vi.fn();

    handleMegaphoneStart(state, client, broadcast);

    expect(client.send).toHaveBeenCalledWith("error", {
      message: "Player not found",
    });
    expect(broadcast).not.toHaveBeenCalled();
  });
});
