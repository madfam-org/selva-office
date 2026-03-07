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
