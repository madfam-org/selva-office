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
  beforeEach(() => {
    // Reset megaphone state
    const broadcast = vi.fn();
    releaseMegaphone("a", broadcast);
    releaseMegaphone("b", broadcast);
  });

  it("allows first player to start megaphone", () => {
    const state = createState();
    addPlayer(state, "a");
    const client = mockClient("a");
    const broadcast = vi.fn();

    handleMegaphoneStart(state, client, broadcast);

    expect(getMegaphoneSpeaker()).toBe("a");
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

    expect(getMegaphoneSpeaker()).toBe("a");
  });

  it("stops megaphone", () => {
    const state = createState();
    addPlayer(state, "a");
    const broadcast = vi.fn();

    handleMegaphoneStart(state, mockClient("a"), broadcast);
    handleMegaphoneStop(mockClient("a"), broadcast);

    expect(getMegaphoneSpeaker()).toBeNull();
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
    handleMegaphoneStop(clientB, broadcast);

    expect(getMegaphoneSpeaker()).toBe("a");
    expect(clientB.send).toHaveBeenCalledWith("error", expect.any(Object));
  });

  it("releases megaphone on disconnect", () => {
    const state = createState();
    addPlayer(state, "a");
    const broadcast = vi.fn();

    handleMegaphoneStart(state, mockClient("a"), broadcast);
    releaseMegaphone("a", broadcast);

    expect(getMegaphoneSpeaker()).toBeNull();
  });
});
