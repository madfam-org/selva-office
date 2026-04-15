/**
 * Agent movement behavior state machine.
 *
 * States:
 * - idle: Slow patrol within home department zone (random waypoints)
 * - working: Stay at current position
 * - waiting_approval: Walk toward nearest review station, stop there
 * - error: Stop in place
 */

interface ZoneBounds {
  x: number;
  y: number;
  width: number;
  height: number;
}

interface ReviewStationPos {
  x: number;
  y: number;
}

/** Idle sub-state for richer stationary animations */
type IdleSubState = 'breathing' | 'looking' | 'stretching';

interface AgentMovementState {
  /** Current behavior state */
  state: 'idle' | 'working' | 'waiting_approval' | 'error';
  /** Target position for movement */
  targetX: number;
  targetY: number;
  /** Time until next waypoint (idle patrol) */
  waypointTimer: number;
  /** Whether the agent has reached the review station */
  atReviewStation: boolean;
  /** Home position (where the agent was spawned) */
  homeX: number;
  homeY: number;
  /** Enhanced idle animation sub-state */
  idleSubState: IdleSubState;
  /** Accumulated time in current idle sub-state (ms) */
  idleSubTimer: number;
}

/** Animation hints returned alongside position data for OfficeScene tweens */
export interface AnimationHint {
  /** Trigger a look-direction change (idle looking sub-state) */
  lookDirection?: 'left' | 'right';
  /** Trigger a stretch tween (idle stretching sub-state) */
  stretch?: boolean;
  /** Working head-bob phase (0-1 sine input) */
  headBobPhase?: number;
  /** Waiting-approval sway offset in px */
  swayOffset?: number;
  /** Error state: reduced alpha */
  errorDim?: boolean;
}

import {
  AGENT_SPEED,
  WAYPOINT_INTERVAL_MIN,
  WAYPOINT_INTERVAL_MAX,
  ARRIVAL_THRESHOLD,
} from './constants';

/** Time between idle sub-state transitions (ms) */
const IDLE_SUB_SWITCH_INTERVAL = 5000;

export class AgentBehavior {
  private states: Map<string, AgentMovementState> = new Map();

  /**
   * Initialize or update behavior state for an agent.
   */
  initAgent(agentId: string, x: number, y: number, status: string): void {
    const existing = this.states.get(agentId);
    if (existing) {
      // Update status transition
      if (existing.state !== status) {
        existing.state = this.mapStatus(status);
        existing.atReviewStation = false;
        if (status === 'idle') {
          // Return to home area
          existing.targetX = existing.homeX;
          existing.targetY = existing.homeY;
          existing.waypointTimer = 1000;
        }
      }
      return;
    }

    this.states.set(agentId, {
      state: this.mapStatus(status),
      targetX: x,
      targetY: y,
      waypointTimer: Math.random() * WAYPOINT_INTERVAL_MAX,
      atReviewStation: false,
      homeX: x,
      homeY: y,
      idleSubState: 'breathing',
      idleSubTimer: 0,
    });
  }

  /**
   * Update agent position based on behavior state.
   * Returns the new position, direction, and animation hints for OfficeScene.
   */
  update(
    agentId: string,
    currentX: number,
    currentY: number,
    delta: number,
    zoneBounds: ZoneBounds | null,
    reviewStation: ReviewStationPos | null,
  ): { x: number; y: number; moving: boolean; direction: string; animHint?: AnimationHint } | null {
    const state = this.states.get(agentId);
    if (!state) return null;

    switch (state.state) {
      case 'idle':
        return this.updateIdle(state, currentX, currentY, delta, zoneBounds);
      case 'working':
        return this.updateWorking(state, currentX, currentY, delta);
      case 'waiting_approval':
        return this.updateWaitingApproval(state, currentX, currentY, delta, reviewStation);
      case 'error':
        return { x: currentX, y: currentY, moving: false, direction: 'down', animHint: { errorDim: true } };
      default:
        return null;
    }
  }

  /**
   * Assign a desk position as the agent's home. When idle the agent will
   * patrol around this position instead of their original spawn point.
   */
  setDeskPosition(agentId: string, x: number, y: number): void {
    const state = this.states.get(agentId);
    if (state) {
      state.homeX = x;
      state.homeY = y;
      // If idle, start walking to the desk
      if (state.state === 'idle') {
        state.targetX = x;
        state.targetY = y;
        state.waypointTimer = 2000;
      }
    }
  }

  removeAgent(agentId: string): void {
    this.states.delete(agentId);
  }

  private mapStatus(status: string): AgentMovementState['state'] {
    switch (status) {
      case 'idle': return 'idle';
      case 'working': return 'working';
      case 'waiting_approval': return 'waiting_approval';
      case 'error': return 'error';
      default: return 'idle';
    }
  }

  private updateIdle(
    state: AgentMovementState,
    currentX: number,
    currentY: number,
    delta: number,
    zoneBounds: ZoneBounds | null,
  ): { x: number; y: number; moving: boolean; direction: string; animHint?: AnimationHint } {
    state.waypointTimer -= delta;

    if (state.waypointTimer <= 0) {
      // Pick a new random waypoint within the zone
      if (zoneBounds) {
        const padding = 16;
        state.targetX = zoneBounds.x + padding + Math.random() * (zoneBounds.width - padding * 2);
        state.targetY = zoneBounds.y + padding + Math.random() * (zoneBounds.height - padding * 2);
      } else {
        // Small random offset from home
        state.targetX = state.homeX + (Math.random() - 0.5) * 60;
        state.targetY = state.homeY + (Math.random() - 0.5) * 60;
      }
      state.waypointTimer = WAYPOINT_INTERVAL_MIN + Math.random() * (WAYPOINT_INTERVAL_MAX - WAYPOINT_INTERVAL_MIN);
    }

    const result = this.moveToward(state, currentX, currentY, delta, AGENT_SPEED);

    // Enhanced idle sub-state animations (only when stationary)
    if (!result.moving) {
      const hint = this.updateIdleSubState(state, delta);
      if (hint) {
        return { ...result, animHint: hint };
      }
    } else {
      // Reset idle sub-state timer when moving
      state.idleSubTimer = 0;
      state.idleSubState = 'breathing';
    }

    return result;
  }

  /**
   * Cycle through idle sub-states (breathing, looking, stretching) and
   * return animation hints for OfficeScene to apply visual tweens.
   */
  private updateIdleSubState(state: AgentMovementState, delta: number): AnimationHint | null {
    state.idleSubTimer += delta;

    if (state.idleSubTimer >= IDLE_SUB_SWITCH_INTERVAL) {
      state.idleSubTimer = 0;
      const states: IdleSubState[] = ['breathing', 'looking', 'stretching'];
      state.idleSubState = states[Math.floor(Math.random() * states.length)];

      switch (state.idleSubState) {
        case 'looking': {
          const dirs: Array<'left' | 'right'> = ['left', 'right'];
          return { lookDirection: dirs[Math.floor(Math.random() * dirs.length)] };
        }
        case 'stretching':
          return { stretch: true };
        default:
          return null;
      }
    }

    return null;
  }

  /**
   * Working state: stationary with a subtle head-bob hint.
   */
  private updateWorking(
    state: AgentMovementState,
    currentX: number,
    currentY: number,
    delta: number,
  ): { x: number; y: number; moving: boolean; direction: string; animHint?: AnimationHint } {
    state.idleSubTimer += delta;
    // Emit a continuous sine phase for head-bob (OfficeScene converts to scaleX tween)
    const phase = (state.idleSubTimer % 2000) / 2000;
    return {
      x: currentX,
      y: currentY,
      moving: false,
      direction: 'down',
      animHint: { headBobPhase: phase },
    };
  }

  private updateWaitingApproval(
    state: AgentMovementState,
    currentX: number,
    currentY: number,
    delta: number,
    reviewStation: ReviewStationPos | null,
  ): { x: number; y: number; moving: boolean; direction: string; animHint?: AnimationHint } {
    if (state.atReviewStation || !reviewStation) {
      // Gentle side-to-side sway while waiting
      state.idleSubTimer += delta;
      const swayPhase = (state.idleSubTimer % 3000) / 3000;
      const swayOffset = Math.sin(swayPhase * Math.PI * 2) * 1;
      return {
        x: currentX,
        y: currentY,
        moving: false,
        direction: 'down',
        animHint: { swayOffset },
      };
    }

    state.targetX = reviewStation.x;
    state.targetY = reviewStation.y - 20; // Stand slightly above the station

    const result = this.moveToward(state, currentX, currentY, delta, AGENT_SPEED * 2);
    if (!result.moving) {
      state.atReviewStation = true;
    }
    return result;
  }

  private moveToward(
    state: AgentMovementState,
    currentX: number,
    currentY: number,
    delta: number,
    speed: number,
  ): { x: number; y: number; moving: boolean; direction: string } {
    const dx = state.targetX - currentX;
    const dy = state.targetY - currentY;
    const dist = Math.sqrt(dx * dx + dy * dy);

    if (dist < ARRIVAL_THRESHOLD) {
      return { x: currentX, y: currentY, moving: false, direction: 'down' };
    }

    const step = speed * (delta / 1000);
    const moveX = (dx / dist) * Math.min(step, dist);
    const moveY = (dy / dist) * Math.min(step, dist);

    // Determine direction for animation
    let direction = 'down';
    if (Math.abs(dx) > Math.abs(dy)) {
      direction = dx > 0 ? 'right' : 'left';
    } else {
      direction = dy > 0 ? 'down' : 'up';
    }

    return {
      x: currentX + moveX,
      y: currentY + moveY,
      moving: true,
      direction,
    };
  }
}
