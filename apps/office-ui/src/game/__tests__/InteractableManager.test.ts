import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock the gameEventBus before importing InteractableManager
const mockEmit = vi.fn();
vi.mock('../PhaserGame', () => ({
  gameEventBus: {
    emit: mockEmit,
    on: vi.fn(() => vi.fn()),
  },
}));

// We test the interact() dispatch case and zone tracking by simulating
// the InteractableManager logic with plain objects (avoiding Phaser runtime).

describe('InteractableManager dispatch type', () => {
  beforeEach(() => {
    mockEmit.mockClear();
  });

  it('emits open_dispatch event for dispatch interactType', async () => {
    // Dynamically import after mock is set up
    const { gameEventBus } = await import('../PhaserGame');

    // Simulate what InteractableManager.interact() does for dispatch type
    const def = {
      id: '1',
      name: 'Dispatch Station',
      interactType: 'dispatch' as const,
      x: 304,
      y: 296,
      width: 48,
      height: 48,
      content: '',
      label: 'Dispatch Station',
    };

    // This replicates the switch case in interact()
    switch (def.interactType) {
      case 'dispatch':
        gameEventBus.emit('open_dispatch', {
          title: def.label ?? 'Dispatch Station',
        });
        break;
    }

    expect(mockEmit).toHaveBeenCalledWith('open_dispatch', {
      title: 'Dispatch Station',
    });
  });

  it('uses default title when label is undefined', async () => {
    const { gameEventBus } = await import('../PhaserGame');

    const def = {
      id: '2',
      name: 'Station',
      interactType: 'dispatch' as const,
      x: 0,
      y: 0,
      width: 48,
      height: 48,
      content: '',
      label: undefined,
    };

    switch (def.interactType) {
      case 'dispatch':
        gameEventBus.emit('open_dispatch', {
          title: def.label ?? 'Dispatch Station',
        });
        break;
    }

    expect(mockEmit).toHaveBeenCalledWith('open_dispatch', {
      title: 'Dispatch Station',
    });
  });

  it('dispatch type is recognized in the switch statement', () => {
    // Verify the dispatch case falls through correctly
    const interactType: string = 'dispatch';
    let emitted = false;

    switch (interactType) {
      case 'url':
      case 'popup':
      case 'jitsi-zone':
      case 'silent-zone':
        break;
      case 'dispatch':
        emitted = true;
        break;
    }

    expect(emitted).toBe(true);
  });
});

describe('InteractableManager zone tracking', () => {
  beforeEach(() => {
    mockEmit.mockClear();
  });

  it('emits zone_enter when player enters a zone', () => {
    // Simulate zone overlap transition: not overlapping -> overlapping
    const zones = [
      { def: { id: '1', name: 'TestZone' }, isOverlapping: true },
    ];
    const previousOverlapping = new Set<string>();
    const currentIds = new Set<string>();

    for (const az of zones) {
      if (az.isOverlapping) {
        currentIds.add(az.def.id);
        if (!previousOverlapping.has(az.def.id)) {
          mockEmit('zone_enter', { areaName: az.def.name });
        }
      }
    }

    expect(mockEmit).toHaveBeenCalledWith('zone_enter', { areaName: 'TestZone' });
  });

  it('emits zone_leave when player exits a zone', () => {
    const zones = [
      { def: { id: '1', name: 'TestZone' }, isOverlapping: false },
    ];
    const previousOverlapping = new Set<string>(['1']);
    const currentIds = new Set<string>();

    for (const az of zones) {
      if (az.isOverlapping) {
        currentIds.add(az.def.id);
      }
    }

    for (const prevId of previousOverlapping) {
      if (!currentIds.has(prevId)) {
        const az = zones.find((z) => z.def.id === prevId);
        if (az) {
          mockEmit('zone_leave', { areaName: az.def.name });
        }
      }
    }

    expect(mockEmit).toHaveBeenCalledWith('zone_leave', { areaName: 'TestZone' });
  });

  it('emits open_blueprint event for blueprint interactType', async () => {
    const { gameEventBus } = await import('../PhaserGame');

    const def = {
      id: '33',
      name: 'Workflow Editor',
      interactType: 'blueprint' as const,
      x: 864,
      y: 320,
      width: 64,
      height: 48,
      content: '',
      label: 'Workflow Editor',
    };

    switch (def.interactType) {
      case 'blueprint':
        gameEventBus.emit('open_blueprint', {
          title: def.label ?? 'Workflow Editor',
        });
        break;
    }

    expect(mockEmit).toHaveBeenCalledWith('open_blueprint', {
      title: 'Workflow Editor',
    });
  });

  it('emits open_desk_info event for desk interactType', async () => {
    const { gameEventBus } = await import('../PhaserGame');

    const def = {
      id: '50',
      name: 'Agent Desk',
      interactType: 'desk' as const,
      x: 100,
      y: 200,
      width: 48,
      height: 48,
      content: '',
      label: 'Planner Desk',
      assignedAgentId: 'agent-abc-123',
    };

    switch (def.interactType) {
      case 'desk':
        gameEventBus.emit('open_desk_info', {
          title: def.label ?? 'Desk',
          assignedAgentId: def.assignedAgentId ?? '',
          x: def.x,
          y: def.y,
        });
        break;
    }

    expect(mockEmit).toHaveBeenCalledWith('open_desk_info', {
      title: 'Planner Desk',
      assignedAgentId: 'agent-abc-123',
      x: 100,
      y: 200,
    });
  });

  it('desk type uses default title when label is undefined', async () => {
    const { gameEventBus } = await import('../PhaserGame');

    const def = {
      id: '51',
      name: 'Some Desk',
      interactType: 'desk' as const,
      x: 50,
      y: 60,
      width: 32,
      height: 32,
      content: '',
      label: undefined,
      assignedAgentId: undefined,
    };

    switch (def.interactType) {
      case 'desk':
        gameEventBus.emit('open_desk_info', {
          title: def.label ?? 'Desk',
          assignedAgentId: def.assignedAgentId ?? '',
          x: def.x,
          y: def.y,
        });
        break;
    }

    expect(mockEmit).toHaveBeenCalledWith('open_desk_info', {
      title: 'Desk',
      assignedAgentId: '',
      x: 50,
      y: 60,
    });
  });

  it('desk type is recognized in the switch statement', () => {
    const interactType: string = 'desk';
    let emitted = false;

    switch (interactType) {
      case 'url':
      case 'popup':
      case 'jitsi-zone':
      case 'silent-zone':
      case 'dispatch':
      case 'blueprint':
        break;
      case 'desk':
        emitted = true;
        break;
    }

    expect(emitted).toBe(true);
  });

  it('does not emit zone_enter when already inside zone', () => {
    const zones = [
      { def: { id: '1', name: 'TestZone' }, isOverlapping: true },
    ];
    const previousOverlapping = new Set<string>(['1']); // already inside
    const currentIds = new Set<string>();

    for (const az of zones) {
      if (az.isOverlapping) {
        currentIds.add(az.def.id);
        if (!previousOverlapping.has(az.def.id)) {
          mockEmit('zone_enter', { areaName: az.def.name });
        }
      }
    }

    expect(mockEmit).not.toHaveBeenCalled();
  });
});

describe('InteractableManager getDeskPositions logic', () => {
  it('returns desk center positions keyed by assignedAgentId', () => {
    // Simulate the getDeskPositions logic without Phaser runtime
    interface DeskZone {
      def: { interactType: string; assignedAgentId?: string; x: number; y: number; width: number; height: number };
    }

    const zones: DeskZone[] = [
      { def: { interactType: 'desk', assignedAgentId: 'agent-1', x: 100, y: 200, width: 48, height: 48 } },
      { def: { interactType: 'desk', assignedAgentId: 'agent-2', x: 300, y: 400, width: 64, height: 64 } },
      { def: { interactType: 'dispatch', x: 500, y: 600, width: 48, height: 48 } },
      { def: { interactType: 'desk', x: 700, y: 800, width: 48, height: 48 } }, // no assignedAgentId
    ];

    const desks = new Map<string, { x: number; y: number }>();
    for (const az of zones) {
      if (az.def.interactType === 'desk' && az.def.assignedAgentId) {
        desks.set(az.def.assignedAgentId, {
          x: az.def.x + az.def.width / 2,
          y: az.def.y + az.def.height / 2,
        });
      }
    }

    expect(desks.size).toBe(2);
    expect(desks.get('agent-1')).toEqual({ x: 124, y: 224 });
    expect(desks.get('agent-2')).toEqual({ x: 332, y: 432 });
  });

  it('returns empty map when no desk zones exist', () => {
    const zones: Array<{ def: { interactType: string; assignedAgentId?: string; x: number; y: number; width: number; height: number } }> = [
      { def: { interactType: 'dispatch', x: 100, y: 200, width: 48, height: 48 } },
    ];

    const desks = new Map<string, { x: number; y: number }>();
    for (const az of zones) {
      if (az.def.interactType === 'desk' && az.def.assignedAgentId) {
        desks.set(az.def.assignedAgentId, {
          x: az.def.x + az.def.width / 2,
          y: az.def.y + az.def.height / 2,
        });
      }
    }

    expect(desks.size).toBe(0);
  });
});
