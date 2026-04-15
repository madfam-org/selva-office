import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";

// Mock livekit-server-sdk before any imports
vi.mock("livekit-server-sdk", () => ({
  AccessToken: vi.fn().mockImplementation(() => ({
    addGrant: vi.fn(),
    ttl: "",
    toJwt: vi.fn().mockResolvedValue("mock-jwt-token"),
  })),
}));

describe("LiveKit handler", () => {
  beforeEach(() => {
    vi.stubEnv("LIVEKIT_API_KEY", "testkey");
    vi.stubEnv("LIVEKIT_API_SECRET", "testsecret");
    vi.stubEnv("LIVEKIT_URL", "ws://localhost:7880");
    vi.stubEnv("LIVEKIT_THRESHOLD", "5");
    // Clear module cache so env vars are re-read
    vi.resetModules();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("isLiveKitEnabled returns true when all env vars set", async () => {
    const { isLiveKitEnabled } = await import("../handlers/livekit");
    expect(isLiveKitEnabled()).toBe(true);
  });

  it("isLiveKitEnabled returns false when API key is missing", async () => {
    vi.stubEnv("LIVEKIT_API_KEY", "");
    vi.resetModules();
    const { isLiveKitEnabled } = await import("../handlers/livekit");
    expect(isLiveKitEnabled()).toBe(false);
  });

  it("isLiveKitEnabled returns false when API secret is missing", async () => {
    vi.stubEnv("LIVEKIT_API_SECRET", "");
    vi.resetModules();
    const { isLiveKitEnabled } = await import("../handlers/livekit");
    expect(isLiveKitEnabled()).toBe(false);
  });

  it("isLiveKitEnabled returns false when URL is missing", async () => {
    vi.stubEnv("LIVEKIT_URL", "");
    vi.resetModules();
    const { isLiveKitEnabled } = await import("../handlers/livekit");
    expect(isLiveKitEnabled()).toBe(false);
  });

  it("generates valid LiveKit token", async () => {
    const { generateLiveKitToken } = await import("../handlers/livekit");
    const token = await generateLiveKitToken("user-123", "Alice", "room-abc");
    expect(token).toBe("mock-jwt-token");
  });

  it("getLiveKitUrl returns the configured URL", async () => {
    const { getLiveKitUrl } = await import("../handlers/livekit");
    expect(getLiveKitUrl()).toBe("ws://localhost:7880");
  });

  it("LIVEKIT_THRESHOLD defaults to 5", async () => {
    vi.stubEnv("LIVEKIT_THRESHOLD", "");
    vi.resetModules();
    const { LIVEKIT_THRESHOLD } = await import("../handlers/livekit");
    // parseInt('', 10) returns NaN, so the fallback '5' in the ?? chain kicks in
    // Actually env is '', which is falsy for ??, so process.env.LIVEKIT_THRESHOLD ?? '5' = '5'
    expect(LIVEKIT_THRESHOLD).toBe(5);
  });

  it("LIVEKIT_THRESHOLD parses custom value", async () => {
    vi.stubEnv("LIVEKIT_THRESHOLD", "10");
    vi.resetModules();
    const { LIVEKIT_THRESHOLD } = await import("../handlers/livekit");
    expect(LIVEKIT_THRESHOLD).toBe(10);
  });
});
