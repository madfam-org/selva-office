import { describe, it, expect, beforeEach } from "vitest";
import { Schema, type, MapSchema } from "@colyseus/schema";
import {
  calculateProximity,
  lockBubble,
  unlockBubble,
  removeFromLockedGroups,
  isInLockedBubble,
} from "../handlers/proximity";
import {
  OfficeStateSchema,
  TacticianSchema,
} from "../schema/OfficeState";

function createState(): OfficeStateSchema {
  const state = new OfficeStateSchema();
  return state;
}

function addPlayer(
  state: OfficeStateSchema,
  sessionId: string,
  x: number,
  y: number
): void {
  const player = new TacticianSchema();
  player.sessionId = sessionId;
  player.x = x;
  player.y = y;
  state.players.set(sessionId, player);
}

describe("calculateProximity", () => {
  it("finds nearby players within radius", () => {
    const state = createState();
    addPlayer(state, "a", 100, 100);
    addPlayer(state, "b", 150, 100); // 50px away — within 200px
    addPlayer(state, "c", 500, 500); // far away

    const groups = calculateProximity(state);
    const groupA = groups.find((g) => g.sessionId === "a");
    expect(groupA?.nearbySessionIds).toContain("b");
    expect(groupA?.nearbySessionIds).not.toContain("c");
  });

  it("returns empty nearby for isolated players", () => {
    const state = createState();
    addPlayer(state, "a", 0, 0);
    addPlayer(state, "b", 1000, 1000);

    const groups = calculateProximity(state);
    const groupA = groups.find((g) => g.sessionId === "a");
    expect(groupA?.nearbySessionIds).toEqual([]);
  });
});

describe("locked bubbles", () => {
  beforeEach(() => {
    // Clean up locked groups between tests by unlocking everything
    // (the module keeps state in a Map)
    unlockBubble("a");
    unlockBubble("b");
    unlockBubble("c");
    unlockBubble("d");
  });

  it("locks a bubble with nearby players", () => {
    const state = createState();
    addPlayer(state, "a", 100, 100);
    addPlayer(state, "b", 120, 100);

    const locked = lockBubble("a", state);
    expect(locked).toBe(true);
    expect(isInLockedBubble("a")).toBe(true);
    expect(isInLockedBubble("b")).toBe(true);
  });

  it("refuses to lock when no nearby players", () => {
    const state = createState();
    addPlayer(state, "a", 0, 0);
    addPlayer(state, "b", 1000, 1000);

    const locked = lockBubble("a", state);
    expect(locked).toBe(false);
    expect(isInLockedBubble("a")).toBe(false);
  });

  it("locked members only see each other in proximity", () => {
    const state = createState();
    addPlayer(state, "a", 100, 100);
    addPlayer(state, "b", 120, 100);
    // c is far from a and b so it won't be in the locked group
    addPlayer(state, "c", 500, 100);

    lockBubble("a", state);

    // Move c close to a (but c is not in the locked group)
    state.players.get("c")!.x = 140;

    const groups = calculateProximity(state);
    const groupA = groups.find((g) => g.sessionId === "a");
    const groupC = groups.find((g) => g.sessionId === "c");

    // a should only see locked member b
    expect(groupA?.nearbySessionIds).toContain("b");
    expect(groupA?.nearbySessionIds).not.toContain("c");
    // c should NOT see locked players a or b
    expect(groupC?.nearbySessionIds).not.toContain("a");
    expect(groupC?.nearbySessionIds).not.toContain("b");
  });

  it("unlocks a bubble", () => {
    const state = createState();
    addPlayer(state, "a", 100, 100);
    addPlayer(state, "b", 120, 100);

    lockBubble("a", state);
    expect(isInLockedBubble("a")).toBe(true);

    unlockBubble("a");
    expect(isInLockedBubble("a")).toBe(false);
    expect(isInLockedBubble("b")).toBe(false);
  });

  it("any member can unlock the bubble", () => {
    const state = createState();
    addPlayer(state, "a", 100, 100);
    addPlayer(state, "b", 120, 100);

    lockBubble("a", state);
    // b is a member, not the owner
    const unlocked = unlockBubble("b");
    expect(unlocked).toBe(true);
    expect(isInLockedBubble("a")).toBe(false);
  });

  it("removes player from locked group on disconnect", () => {
    const state = createState();
    addPlayer(state, "a", 100, 100);
    addPlayer(state, "b", 120, 100);
    addPlayer(state, "c", 140, 100);

    lockBubble("a", state);
    // Remove b from group
    removeFromLockedGroups("b");
    // a and c should still be in group (if c was nearby)
    expect(isInLockedBubble("a")).toBe(true);
  });

  it("dissolves group when only one member left", () => {
    const state = createState();
    addPlayer(state, "a", 100, 100);
    addPlayer(state, "b", 120, 100);

    lockBubble("a", state);
    removeFromLockedGroups("b");
    // Only a left — group should dissolve
    expect(isInLockedBubble("a")).toBe(false);
  });

  it("refuses double-lock", () => {
    const state = createState();
    addPlayer(state, "a", 100, 100);
    addPlayer(state, "b", 120, 100);

    lockBubble("a", state);
    const secondLock = lockBubble("a", state);
    expect(secondLock).toBe(false);
  });
});
