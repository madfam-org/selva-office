/**
 * Per-session message throttler for Colyseus rooms.
 *
 * Uses a 1-second rolling window per session.  High-frequency message
 * types (e.g. "move", "webrtc_signal") can be exempted so they are
 * never throttled.
 */
export class MessageThrottler {
  private counts = new Map<string, { count: number; resetAt: number }>();
  private maxPerSecond: number;
  private exemptTypes: Set<string>;

  constructor(
    maxPerSecond = 30,
    exemptTypes: string[] = ["move", "webrtc_signal"],
  ) {
    this.maxPerSecond = maxPerSecond;
    this.exemptTypes = new Set(exemptTypes);
  }

  /**
   * Return `true` if the message should be processed, `false` if
   * the session has exceeded the per-second budget for non-exempt
   * message types.
   */
  check(sessionId: string, messageType: string): boolean {
    if (this.exemptTypes.has(messageType)) return true;

    const now = Date.now();
    let entry = this.counts.get(sessionId);
    if (!entry || now >= entry.resetAt) {
      entry = { count: 0, resetAt: now + 1000 };
      this.counts.set(sessionId, entry);
    }
    entry.count++;
    return entry.count <= this.maxPerSecond;
  }

  /** Remove state for a disconnected session. */
  remove(sessionId: string): void {
    this.counts.delete(sessionId);
  }
}
