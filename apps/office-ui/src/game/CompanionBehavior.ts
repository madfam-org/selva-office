/**
 * Companion behavior: follows the owner with a slight lag.
 * Companions are small sprites that trail behind the player.
 */

import { COMPANION_SPEED, FOLLOW_DISTANCE, LAG_FACTOR } from './constants';

interface CompanionState {
  x: number;
  y: number;
  targetX: number;
  targetY: number;
  direction: string;
  /** Accumulated idle time for bob animation (ms) */
  idleTime: number;
  /** Whether the companion is currently bobbing (owner stationary) */
  isBobbing: boolean;
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
      idleTime: 0,
      isBobbing: false,
    });
  }

  update(
    sessionId: string,
    ownerX: number,
    ownerY: number,
    delta: number,
  ): { x: number; y: number; direction: string; moving: boolean; bobOffset: number } | null {
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
      // Reset idle bob when moving
      state.idleTime = 0;
      state.isBobbing = false;
      return { x: state.x, y: state.y, direction: state.direction, moving: true, bobOffset: 0 };
    }

    // Stationary: gentle bob animation
    state.idleTime += delta;
    state.isBobbing = true;
    const bobPhase = (state.idleTime % 2000) / 2000;
    const bobOffset = Math.sin(bobPhase * Math.PI * 2) * -1; // -1px to +1px vertical

    return { x: state.x, y: state.y + bobOffset, direction: state.direction, moving: false, bobOffset };
  }

  removeCompanion(sessionId: string): void {
    this.companions.delete(sessionId);
  }
}
