import { describe, it, expect, vi } from "vitest";

// Replicate the GameEventBus class from PhaserGame.tsx for isolated testing
class GameEventBus extends EventTarget {
  private lastValue = new Map<string, unknown>();

  emit(event: string, detail?: unknown) {
    this.lastValue.set(event, detail);
    this.dispatchEvent(new CustomEvent(event, { detail }));
  }

  on(event: string, callback: (detail: unknown) => void) {
    const handler = (e: Event) => callback((e as CustomEvent).detail);
    this.addEventListener(event, handler);
    const cached = this.lastValue.get(event);
    if (cached !== undefined) {
      callback(cached);
    }
    return () => this.removeEventListener(event, handler);
  }
}

describe("GameEventBus", () => {
  it("delivers events to active subscribers", () => {
    const bus = new GameEventBus();
    const cb = vi.fn();

    bus.on("test", cb);
    bus.emit("test", { value: 42 });

    expect(cb).toHaveBeenCalledTimes(1);
    expect(cb).toHaveBeenCalledWith({ value: 42 });
  });

  it("replays cached value to late subscribers", () => {
    const bus = new GameEventBus();
    const cb = vi.fn();

    // Emit BEFORE subscribing
    bus.emit("state-update", { departments: [] });

    // Late subscriber should receive the cached value immediately
    bus.on("state-update", cb);

    expect(cb).toHaveBeenCalledTimes(1);
    expect(cb).toHaveBeenCalledWith({ departments: [] });
  });

  it("replays only the latest cached value", () => {
    const bus = new GameEventBus();
    const cb = vi.fn();

    bus.emit("state-update", { v: 1 });
    bus.emit("state-update", { v: 2 });
    bus.emit("state-update", { v: 3 });

    bus.on("state-update", cb);

    // Should only receive the most recent value
    expect(cb).toHaveBeenCalledTimes(1);
    expect(cb).toHaveBeenCalledWith({ v: 3 });
  });

  it("does not replay if no value was cached for that event", () => {
    const bus = new GameEventBus();
    const cb = vi.fn();

    bus.on("unrelated-event", cb);

    expect(cb).not.toHaveBeenCalled();
  });

  it("late subscriber still receives future events after replay", () => {
    const bus = new GameEventBus();
    const cb = vi.fn();

    bus.emit("data", "cached");
    bus.on("data", cb);

    // First call: replay
    expect(cb).toHaveBeenCalledTimes(1);

    // Second call: new event
    bus.emit("data", "live");
    expect(cb).toHaveBeenCalledTimes(2);
    expect(cb).toHaveBeenLastCalledWith("live");
  });

  it("unsubscribe stops future events but not replay", () => {
    const bus = new GameEventBus();
    const cb = vi.fn();

    bus.emit("data", "cached");
    const unsub = bus.on("data", cb);

    // Replay happened
    expect(cb).toHaveBeenCalledTimes(1);

    unsub();
    bus.emit("data", "after-unsub");

    // Should not receive the post-unsub event
    expect(cb).toHaveBeenCalledTimes(1);
  });

  it("caches different events independently", () => {
    const bus = new GameEventBus();
    const cbA = vi.fn();
    const cbB = vi.fn();

    bus.emit("event-a", "alpha");
    bus.emit("event-b", "beta");

    bus.on("event-a", cbA);
    bus.on("event-b", cbB);

    expect(cbA).toHaveBeenCalledWith("alpha");
    expect(cbB).toHaveBeenCalledWith("beta");
  });
});
