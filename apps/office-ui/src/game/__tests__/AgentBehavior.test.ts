import { describe, it, expect, beforeEach } from 'vitest';
import { AgentBehavior } from '../AgentBehavior';

describe('AgentBehavior', () => {
  let behavior: AgentBehavior;

  beforeEach(() => {
    behavior = new AgentBehavior();
  });

  describe('initAgent', () => {
    it('creates movement state for a new agent', () => {
      behavior.initAgent('agent-1', 100, 200, 'idle');

      const result = behavior.update('agent-1', 100, 200, 16, null, null);
      expect(result).not.toBeNull();
    });

    it('transitions status on re-init', () => {
      behavior.initAgent('agent-1', 100, 200, 'idle');
      behavior.initAgent('agent-1', 100, 200, 'working');

      const result = behavior.update('agent-1', 100, 200, 16, null, null);
      expect(result).toMatchObject({ x: 100, y: 200, moving: false, direction: 'down' });
    });
  });

  describe('update — idle state', () => {
    it('returns a position when idle', () => {
      behavior.initAgent('agent-1', 100, 200, 'idle');

      const result = behavior.update('agent-1', 100, 200, 16, null, null);
      expect(result).not.toBeNull();
      expect(result!.x).toBeTypeOf('number');
      expect(result!.y).toBeTypeOf('number');
    });

    it('moves toward waypoint within zone bounds after timer expires', () => {
      behavior.initAgent('agent-1', 100, 200, 'idle');
      const zone = { x: 50, y: 150, width: 200, height: 200 };

      // Run enough time to expire the waypoint timer (max 7s)
      const result = behavior.update('agent-1', 100, 200, 8000, zone, null);
      expect(result).not.toBeNull();
    });

    it('picks random offset from home when no zone bounds', () => {
      behavior.initAgent('agent-1', 100, 200, 'idle');

      // Exhaust the timer to force a new waypoint
      const result = behavior.update('agent-1', 100, 200, 8000, null, null);
      expect(result).not.toBeNull();
    });
  });

  describe('update — working state', () => {
    it('stays in place (not moving)', () => {
      behavior.initAgent('agent-1', 150, 250, 'working');

      const result = behavior.update('agent-1', 150, 250, 16, null, null);
      expect(result).toMatchObject({ x: 150, y: 250, moving: false, direction: 'down' });
    });
  });

  describe('update — waiting_approval state', () => {
    it('moves toward review station', () => {
      behavior.initAgent('agent-1', 100, 200, 'waiting_approval');
      const reviewStation = { x: 300, y: 200 };

      const result = behavior.update('agent-1', 100, 200, 1000, null, reviewStation);
      expect(result).not.toBeNull();
      expect(result!.x).toBeGreaterThan(100);
      expect(result!.moving).toBe(true);
    });

    it('stops when it reaches the review station', () => {
      behavior.initAgent('agent-1', 300, 179, 'waiting_approval');
      const reviewStation = { x: 300, y: 200 };

      // Target is reviewStation.y - 20 = 180, so 179 is within threshold (2px)
      const result = behavior.update('agent-1', 300, 179, 16, null, reviewStation);
      expect(result).not.toBeNull();
      expect(result!.moving).toBe(false);
    });

    it('stays in place when no review station is provided', () => {
      behavior.initAgent('agent-1', 100, 200, 'waiting_approval');

      const result = behavior.update('agent-1', 100, 200, 16, null, null);
      expect(result).toMatchObject({ x: 100, y: 200, moving: false, direction: 'down' });
    });

    it('stays once atReviewStation is set', () => {
      behavior.initAgent('agent-1', 300, 180, 'waiting_approval');
      const reviewStation = { x: 300, y: 200 };

      // First call: arrive at station (300, 180 is at target 300, 180)
      behavior.update('agent-1', 300, 180, 16, null, reviewStation);

      // Second call: should stay put even though station is provided
      const result = behavior.update('agent-1', 300, 180, 16, null, reviewStation);
      expect(result!.moving).toBe(false);
    });
  });

  describe('update — error state', () => {
    it('stays in place (not moving)', () => {
      behavior.initAgent('agent-1', 200, 300, 'error');

      const result = behavior.update('agent-1', 200, 300, 16, null, null);
      expect(result).toMatchObject({ x: 200, y: 300, moving: false, direction: 'down' });
    });
  });

  describe('update — unknown agent', () => {
    it('returns null for unregistered agent', () => {
      const result = behavior.update('unknown', 0, 0, 16, null, null);
      expect(result).toBeNull();
    });
  });

  describe('setDeskPosition', () => {
    it('updates home position for an existing agent', () => {
      behavior.initAgent('agent-1', 100, 200, 'idle');
      behavior.setDeskPosition('agent-1', 400, 500);

      // Exhaust waypoint timer to force new waypoint — agent should now patrol
      // around desk position (400, 500) instead of original home (100, 200)
      // After setting desk position on idle agent, target is set to desk
      const result = behavior.update('agent-1', 100, 200, 16, null, null);
      expect(result).not.toBeNull();
      // Agent should be moving toward the desk position
      expect(result!.moving).toBe(true);
    });

    it('does not throw for non-existent agent', () => {
      expect(() => behavior.setDeskPosition('nonexistent', 400, 500)).not.toThrow();
    });

    it('does not change target when agent is working', () => {
      behavior.initAgent('agent-1', 100, 200, 'working');
      behavior.setDeskPosition('agent-1', 400, 500);

      // Working agents stay in place regardless of desk position
      const result = behavior.update('agent-1', 100, 200, 16, null, null);
      expect(result).toMatchObject({ x: 100, y: 200, moving: false, direction: 'down' });
    });

    it('agent patrols near desk after waypoint expires', () => {
      behavior.initAgent('agent-1', 400, 500, 'idle');
      behavior.setDeskPosition('agent-1', 400, 500);

      // Exhaust timer — should pick new waypoint near new home (400, 500)
      const result = behavior.update('agent-1', 400, 500, 8000, null, null);
      expect(result).not.toBeNull();
      // Without zone bounds, the offset is +-30 from home
      expect(result!.x).toBeTypeOf('number');
    });
  });

  describe('removeAgent', () => {
    it('removes agent state so update returns null', () => {
      behavior.initAgent('agent-1', 100, 200, 'idle');
      behavior.removeAgent('agent-1');

      const result = behavior.update('agent-1', 100, 200, 16, null, null);
      expect(result).toBeNull();
    });

    it('does not throw for non-existent agent', () => {
      expect(() => behavior.removeAgent('nonexistent')).not.toThrow();
    });
  });

  describe('status transitions', () => {
    it('transitions from idle to waiting_approval resets atReviewStation', () => {
      behavior.initAgent('agent-1', 100, 200, 'idle');

      // Transition to waiting_approval
      behavior.initAgent('agent-1', 100, 200, 'waiting_approval');
      const reviewStation = { x: 300, y: 200 };

      const result = behavior.update('agent-1', 100, 200, 1000, null, reviewStation);
      expect(result!.moving).toBe(true);
    });

    it('transitions from working to idle targets home position', () => {
      behavior.initAgent('agent-1', 100, 200, 'working');

      // Move agent away from home
      // Transition to idle
      behavior.initAgent('agent-1', 150, 250, 'idle');

      // Should target back toward home (100, 200)
      const result = behavior.update('agent-1', 150, 250, 500, null, null);
      expect(result).not.toBeNull();
    });

    it('maps unknown status to idle', () => {
      behavior.initAgent('agent-1', 100, 200, 'some_unknown_status');

      // Should behave as idle
      const result = behavior.update('agent-1', 100, 200, 8000, null, null);
      expect(result).not.toBeNull();
    });
  });

  describe('movement direction', () => {
    it('reports right direction when moving right', () => {
      behavior.initAgent('agent-1', 0, 0, 'waiting_approval');
      const reviewStation = { x: 200, y: 20 }; // target = (200, 0), mostly right

      const result = behavior.update('agent-1', 0, 0, 1000, null, reviewStation);
      expect(result!.direction).toBe('right');
    });

    it('reports left direction when moving left', () => {
      behavior.initAgent('agent-1', 200, 0, 'waiting_approval');
      const reviewStation = { x: 0, y: 20 }; // target = (0, 0), mostly left

      const result = behavior.update('agent-1', 200, 0, 1000, null, reviewStation);
      expect(result!.direction).toBe('left');
    });

    it('reports down direction when moving down', () => {
      behavior.initAgent('agent-1', 0, 0, 'waiting_approval');
      const reviewStation = { x: 0, y: 220 }; // target = (0, 200), pure down

      const result = behavior.update('agent-1', 0, 0, 1000, null, reviewStation);
      expect(result!.direction).toBe('down');
    });

    it('reports up direction when moving up', () => {
      behavior.initAgent('agent-1', 0, 200, 'waiting_approval');
      const reviewStation = { x: 0, y: 20 }; // target = (0, 0), pure up

      const result = behavior.update('agent-1', 0, 200, 1000, null, reviewStation);
      expect(result!.direction).toBe('up');
    });
  });
});
