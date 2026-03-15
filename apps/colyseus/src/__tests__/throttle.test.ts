import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { MessageThrottler } from "../throttle";

describe("MessageThrottler", () => {
  let throttler: MessageThrottler;

  beforeEach(() => {
    // Allow 5 messages per second for easier testing
    throttler = new MessageThrottler(5, ["move", "webrtc_signal"]);
  });

  it("allows messages under the limit", () => {
    for (let i = 0; i < 5; i++) {
      expect(throttler.check("session-1", "chat")).toBe(true);
    }
  });

  it("blocks messages over the limit", () => {
    for (let i = 0; i < 5; i++) {
      throttler.check("session-1", "chat");
    }
    // The 6th message should be blocked
    expect(throttler.check("session-1", "chat")).toBe(false);
    expect(throttler.check("session-1", "emote")).toBe(false);
  });

  it("resets after the 1-second window elapses", () => {
    vi.useFakeTimers();
    try {
      for (let i = 0; i < 5; i++) {
        throttler.check("session-1", "chat");
      }
      expect(throttler.check("session-1", "chat")).toBe(false);

      // Advance time past the 1-second window
      vi.advanceTimersByTime(1001);

      expect(throttler.check("session-1", "chat")).toBe(true);
    } finally {
      vi.useRealTimers();
    }
  });

  it("exempt types are always allowed regardless of budget", () => {
    // Exhaust the budget with non-exempt messages
    for (let i = 0; i < 5; i++) {
      throttler.check("session-1", "chat");
    }
    // Non-exempt should now be blocked
    expect(throttler.check("session-1", "chat")).toBe(false);

    // Exempt types should still pass
    expect(throttler.check("session-1", "move")).toBe(true);
    expect(throttler.check("session-1", "webrtc_signal")).toBe(true);
  });

  it("tracks sessions independently", () => {
    for (let i = 0; i < 5; i++) {
      throttler.check("session-1", "chat");
    }
    expect(throttler.check("session-1", "chat")).toBe(false);

    // session-2 should have its own budget
    expect(throttler.check("session-2", "chat")).toBe(true);
  });

  it("remove() cleans up session state", () => {
    for (let i = 0; i < 5; i++) {
      throttler.check("session-1", "chat");
    }
    expect(throttler.check("session-1", "chat")).toBe(false);

    // Remove and verify the session gets a fresh budget
    throttler.remove("session-1");
    expect(throttler.check("session-1", "chat")).toBe(true);
  });

  it("remove() is safe to call for unknown sessions", () => {
    // Should not throw
    throttler.remove("nonexistent-session");
  });

  it("uses default constructor values when none provided", () => {
    const defaultThrottler = new MessageThrottler();
    // Default is 30 messages/s -- send 30, all should pass
    for (let i = 0; i < 30; i++) {
      expect(defaultThrottler.check("s1", "chat")).toBe(true);
    }
    expect(defaultThrottler.check("s1", "chat")).toBe(false);
    // Defaults exempt "move" and "webrtc_signal"
    expect(defaultThrottler.check("s1", "move")).toBe(true);
    expect(defaultThrottler.check("s1", "webrtc_signal")).toBe(true);
  });
});
