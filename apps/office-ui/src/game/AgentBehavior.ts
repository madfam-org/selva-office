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
}

const AGENT_SPEED = 30; // pixels per second (slow patrol)
const WAYPOINT_INTERVAL_MIN = 3000; // ms
const WAYPOINT_INTERVAL_MAX = 7000; // ms
const ARRIVAL_THRESHOLD = 2; // pixels

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
    });
  }

  /**
   * Update agent position based on behavior state.
   * Returns the new position and direction for animation.
   */
  update(
    agentId: string,
    currentX: number,
    currentY: number,
    delta: number,
    zoneBounds: ZoneBounds | null,
    reviewStation: ReviewStationPos | null,
  ): { x: number; y: number; moving: boolean; direction: string } | null {
    const state = this.states.get(agentId);
    if (!state) return null;

    switch (state.state) {
      case 'idle':
        return this.updateIdle(state, currentX, currentY, delta, zoneBounds);
      case 'working':
        return { x: currentX, y: currentY, moving: false, direction: 'down' };
      case 'waiting_approval':
        return this.updateWaitingApproval(state, currentX, currentY, delta, reviewStation);
      case 'error':
        return { x: currentX, y: currentY, moving: false, direction: 'down' };
      default:
        return null;
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
  ): { x: number; y: number; moving: boolean; direction: string } {
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

    return this.moveToward(state, currentX, currentY, delta, AGENT_SPEED);
  }

  private updateWaitingApproval(
    state: AgentMovementState,
    currentX: number,
    currentY: number,
    delta: number,
    reviewStation: ReviewStationPos | null,
  ): { x: number; y: number; moving: boolean; direction: string } {
    if (state.atReviewStation || !reviewStation) {
      return { x: currentX, y: currentY, moving: false, direction: 'down' };
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
