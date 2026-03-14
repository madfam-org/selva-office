/**
 * Companion behavior: follows the owner with a slight lag.
 * Companions are small sprites that trail behind the player.
 */

const COMPANION_SPEED = 180; // slightly slower than player (200)
const FOLLOW_DISTANCE = 28; // pixels behind owner
const LAG_FACTOR = 0.08; // interpolation lag (lower = more delay)

interface CompanionState {
  x: number;
  y: number;
  targetX: number;
  targetY: number;
  direction: string;
}

export class CompanionBehavior {
  private companions: Map<string, CompanionState> = new Map();

  initCompanion(sessionId: string, ownerX: number, ownerY: number): void {
    this.companions.set(sessionId, {
      x: ownerX,
      y: ownerY + FOLLOW_DISTANCE,
      targetX: ownerX,
      targetY: ownerY + FOLLOW_DISTANCE,
      direction: 'down',
    });
  }

  update(
    sessionId: string,
    ownerX: number,
    ownerY: number,
    delta: number,
  ): { x: number; y: number; direction: string; moving: boolean } | null {
    const state = this.companions.get(sessionId);
    if (!state) return null;

    // Target: slightly behind the owner
    state.targetX = ownerX;
    state.targetY = ownerY + FOLLOW_DISTANCE;

    // Lerp toward target with lag
    const dx = state.targetX - state.x;
    const dy = state.targetY - state.y;
    const dist = Math.sqrt(dx * dx + dy * dy);

    if (dist > 2) {
      const step = Math.min(COMPANION_SPEED * (delta / 1000), dist);
      state.x += (dx / dist) * step * LAG_FACTOR * 10;
      state.y += (dy / dist) * step * LAG_FACTOR * 10;

      if (Math.abs(dx) > Math.abs(dy)) {
        state.direction = dx > 0 ? 'right' : 'left';
      } else {
        state.direction = dy > 0 ? 'down' : 'up';
      }
      return { x: state.x, y: state.y, direction: state.direction, moving: true };
    }

    return { x: state.x, y: state.y, direction: state.direction, moving: false };
  }

  removeCompanion(sessionId: string): void {
    this.companions.delete(sessionId);
  }
}
