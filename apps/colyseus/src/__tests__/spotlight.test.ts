import { describe, it, expect, beforeEach, vi } from "vitest";
import {
  handleSpotlightStart,
  handleSpotlightStop,
  releaseSpotlight,
  getSpotlightPresenter,
} from "../handlers/spotlight";
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

describe("spotlight", () => {
  beforeEach(() => {
    // Reset spotlight state by releasing any active presenter
    const state = createState();
    const broadcast = vi.fn();
    releaseSpotlight("a", state, broadcast);
    releaseSpotlight("b", state, broadcast);
  });

  it("allows first player to start spotlight", () => {
    const state = createState();
    addPlayer(state, "a");
    const client = mockClient("a");
    const broadcast = vi.fn();

    handleSpotlightStart(state, client, broadcast);

    expect(getSpotlightPresenter()).toBe("a");
    expect(state.spotlightPresenter).toBe("a");
    expect(broadcast).toHaveBeenCalledWith("spotlight_active", {
      sessionId: "a",
      name: "Player-a",
      active: true,
    });
  });

  it("stops spotlight", () => {
    const state = createState();
    addPlayer(state, "a");
    const broadcast = vi.fn();

    handleSpotlightStart(state, mockClient("a"), broadcast);
    handleSpotlightStop(mockClient("a"), state, broadcast);

    expect(getSpotlightPresenter()).toBeNull();
    expect(state.spotlightPresenter).toBe("");
    expect(broadcast).toHaveBeenLastCalledWith("spotlight_active", {
      sessionId: "a",
      active: false,
    });
  });

  it("blocks second player when spotlight already in use", () => {
    const state = createState();
    addPlayer(state, "a");
    addPlayer(state, "b");
    const clientB = mockClient("b");
    const broadcast = vi.fn();

    handleSpotlightStart(state, mockClient("a"), broadcast);
    handleSpotlightStart(state, clientB, broadcast);

    expect(getSpotlightPresenter()).toBe("a");
    expect(clientB.send).toHaveBeenCalledWith("error", {
      message: "Spotlight already in use",
    });
  });

  it("rejects stop from non-presenter", () => {
    const state = createState();
    addPlayer(state, "a");
    const clientB = mockClient("b");
    const broadcast = vi.fn();

    handleSpotlightStart(state, mockClient("a"), broadcast);
    handleSpotlightStop(clientB, state, broadcast);

    expect(getSpotlightPresenter()).toBe("a");
    expect(clientB.send).toHaveBeenCalledWith("error", {
      message: "You are not the spotlight presenter",
    });
  });

  it("releases spotlight on disconnect", () => {
    const state = createState();
    addPlayer(state, "a");
    const broadcast = vi.fn();

    handleSpotlightStart(state, mockClient("a"), broadcast);
    releaseSpotlight("a", state, broadcast);

    expect(getSpotlightPresenter()).toBeNull();
    expect(state.spotlightPresenter).toBe("");
    expect(broadcast).toHaveBeenLastCalledWith("spotlight_active", {
      sessionId: "a",
      active: false,
    });
  });

  it("has spotlightPresenter field on schema with correct default", () => {
    const state = createState();
    expect(state.spotlightPresenter).toBe("");
  });
});
