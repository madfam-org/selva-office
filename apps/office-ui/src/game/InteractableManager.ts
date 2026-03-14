import Phaser from 'phaser';
import { gameEventBus } from './PhaserGame';

export type InteractType = 'url' | 'popup' | 'jitsi-zone' | 'silent-zone' | 'dispatch' | 'blueprint' | 'desk' | 'restricted-zone';

export interface InteractableDef {
  id: string;
  name: string;
  interactType: InteractType;
  x: number;
  y: number;
  width: number;
  height: number;
  /** URL for 'url' type, text content for 'popup' type */
  content: string;
  /** Optional label shown when player is in proximity */
  label?: string;
  /** Agent ID assigned to this desk (desk interactType only) */
  assignedAgentId?: string;
  /** Comma-separated tags required to enter (restricted-zone only) */
  requiredTags?: string;
}

interface ActiveZone {
  def: InteractableDef;
  zone: Phaser.GameObjects.Zone;
  prompt: Phaser.GameObjects.Text;
  isOverlapping: boolean;
}

const INTERACT_TYPES: InteractType[] = ['url', 'popup', 'jitsi-zone', 'silent-zone', 'dispatch', 'blueprint', 'desk', 'restricted-zone'];

/**
 * Manages interactive map objects parsed from Tiled object layer 'interactables'.
 * Creates overlap zones and dispatches events via GameEventBus when the player
 * presses E (buttonX) near an interactable.
 */
export class InteractableManager {
  private scene: Phaser.Scene;
  private zones: ActiveZone[] = [];
  private playerSprite: Phaser.GameObjects.Sprite;
  private currentOverlap: ActiveZone | null = null;
  private inSilentZone: boolean = false;
  private overlappingZoneIds: Set<string> = new Set();
  private playerTags: Set<string> = new Set();
  private restrictedDeniedZoneId: string | null = null;

  constructor(scene: Phaser.Scene, playerSprite: Phaser.GameObjects.Sprite) {
    this.scene = scene;
    this.playerSprite = playerSprite;
  }

  /** Set the player's tags/roles for restricted zone access checks. */
  setPlayerTags(tags: string[]): void {
    this.playerTags = new Set(tags);
  }

  /**
   * Parse interactable objects from a Tiled tilemap's 'interactables' object layer.
   */
  loadFromTilemap(tilemap: Phaser.Tilemaps.Tilemap): void {
    const objectLayer = tilemap.getObjectLayer('interactables');
    if (!objectLayer) return;

    for (const obj of objectLayer.objects) {
      const interactType = this.getProp(obj, 'interactType') as string | undefined;
      if (!interactType || !INTERACT_TYPES.includes(interactType as InteractType)) continue;

      const def: InteractableDef = {
        id: String(obj.id ?? obj.name ?? Math.random().toString(36).slice(2)),
        name: obj.name ?? 'Interactable',
        interactType: interactType as InteractType,
        x: obj.x ?? 0,
        y: obj.y ?? 0,
        width: obj.width ?? 32,
        height: obj.height ?? 32,
        content: (this.getProp(obj, 'content') as string) ?? '',
        label: (this.getProp(obj, 'label') as string) ?? undefined,
        assignedAgentId: (this.getProp(obj, 'assignedAgentId') as string) ?? undefined,
        requiredTags: (this.getProp(obj, 'requiredTags') as string) ?? undefined,
      };

      this.createZone(def);
    }
  }

  /**
   * Add interactables from an array of definitions (for procedural/fallback maps).
   */
  addInteractables(defs: InteractableDef[]): void {
    for (const def of defs) {
      this.createZone(def);
    }
  }

  /**
   * Call once per frame from the scene's update(). Checks overlap with
   * the player sprite and shows/hides interaction prompts.
   */
  update(): void {
    let closestZone: ActiveZone | null = null;
    let closestDist = Infinity;

    for (const az of this.zones) {
      const bounds = az.zone.getBounds();
      const playerX = this.playerSprite.x;
      const playerY = this.playerSprite.y;

      const overlapping =
        playerX >= bounds.left &&
        playerX <= bounds.right &&
        playerY >= bounds.top &&
        playerY <= bounds.bottom;

      az.isOverlapping = overlapping;

      if (overlapping) {
        const dist = Phaser.Math.Distance.Between(
          playerX,
          playerY,
          bounds.centerX,
          bounds.centerY,
        );
        if (dist < closestDist) {
          closestDist = dist;
          closestZone = az;
        }
      }
    }

    // Update prompt visibility
    for (const az of this.zones) {
      const isAutoZone = az.def.interactType === 'silent-zone' || az.def.interactType === 'restricted-zone';
      const shouldShow = az === closestZone && !isAutoZone;
      az.prompt.setVisible(shouldShow);
      if (shouldShow) {
        const promptX = Phaser.Math.Clamp(this.playerSprite.x, 60, (this.scene.scale.width || 1280) - 60);
        const promptY = Math.max(20, this.playerSprite.y - 40);
        az.prompt.setPosition(promptX, promptY);
      }
    }

    // Handle restricted zone access check
    for (const az of this.zones) {
      if (az.isOverlapping && az.def.interactType === 'restricted-zone' && az.def.requiredTags) {
        const required = az.def.requiredTags.split(',').map((t) => t.trim());
        const hasAccess = required.some((tag) => this.playerTags.has(tag));
        if (!hasAccess) {
          // Push player out of the restricted zone
          const bounds = az.zone.getBounds();
          const cx = bounds.centerX;
          const cy = bounds.centerY;
          const dx = this.playerSprite.x - cx;
          const dy = this.playerSprite.y - cy;
          const dist = Math.max(1, Math.sqrt(dx * dx + dy * dy));
          // Push back to edge + 4px margin
          this.playerSprite.x = cx + (dx / dist) * (bounds.width / 2 + 4);
          this.playerSprite.y = cy + (dy / dist) * (bounds.height / 2 + 4);
          az.isOverlapping = false;
          // Emit access denied once per zone entry attempt
          if (this.restrictedDeniedZoneId !== az.def.id) {
            this.restrictedDeniedZoneId = az.def.id;
            gameEventBus.emit('access_denied', {
              zoneName: az.def.label ?? az.def.name,
              requiredTags: required,
            });
          }
        }
      }
    }
    // Clear denied zone when no longer overlapping any restricted zone
    const stillInRestricted = this.zones.some(
      (az) => az.isOverlapping && az.def.interactType === 'restricted-zone',
    );
    if (!stillInRestricted) {
      this.restrictedDeniedZoneId = null;
    }

    // Handle silent zone enter/exit
    const inSilentNow = this.zones.some(
      (az) => az.isOverlapping && az.def.interactType === 'silent-zone',
    );
    if (inSilentNow !== this.inSilentZone) {
      this.inSilentZone = inSilentNow;
      gameEventBus.emit(
        inSilentNow ? 'silent_zone_enter' : 'silent_zone_exit',
        null,
      );
    }

    // Track zone enter/leave for scripting API
    const currentIds = new Set<string>();
    for (const az of this.zones) {
      if (az.isOverlapping) {
        currentIds.add(az.def.id);
        if (!this.overlappingZoneIds.has(az.def.id)) {
          gameEventBus.emit('zone_enter', { areaName: az.def.name });
        }
      }
    }
    for (const prevId of this.overlappingZoneIds) {
      if (!currentIds.has(prevId)) {
        const az = this.zones.find((z) => z.def.id === prevId);
        if (az) {
          gameEventBus.emit('zone_leave', { areaName: az.def.name });
        }
      }
    }
    this.overlappingZoneIds = currentIds;

    this.currentOverlap = closestZone;
  }

  /**
   * Trigger interaction with the currently overlapping interactable.
   * Called when the player presses E (buttonX).
   */
  interact(): void {
    if (!this.currentOverlap) return;

    const def = this.currentOverlap.def;
    switch (def.interactType) {
      case 'url':
        gameEventBus.emit('open_cowebsite', {
          url: def.content,
          title: def.label ?? def.name,
        });
        break;
      case 'popup':
        gameEventBus.emit('show_popup', {
          title: def.label ?? def.name,
          content: def.content,
        });
        break;
      case 'jitsi-zone':
        gameEventBus.emit('open_cowebsite', {
          url: def.content,
          title: def.label ?? 'Video Meeting',
        });
        break;
      case 'dispatch':
        gameEventBus.emit('open_dispatch', {
          title: def.label ?? 'Dispatch Station',
        });
        break;
      case 'blueprint':
        gameEventBus.emit('open_blueprint', {
          title: def.label ?? 'Workflow Editor',
        });
        break;
      case 'desk':
        gameEventBus.emit('open_desk_info', {
          title: def.label ?? 'Desk',
          assignedAgentId: def.assignedAgentId ?? '',
          x: def.x,
          y: def.y,
        });
        break;
      // silent-zone handled in update() via enter/exit events
    }
  }

  /** Whether the player is currently overlapping any interactable */
  hasActiveOverlap(): boolean {
    return this.currentOverlap !== null;
  }

  /**
   * Return a map of agentId -> desk center position for all desk interactables
   * that have an assignedAgentId property.
   */
  getDeskPositions(): Map<string, { x: number; y: number }> {
    const desks = new Map<string, { x: number; y: number }>();
    for (const az of this.zones) {
      if (az.def.interactType === 'desk' && az.def.assignedAgentId) {
        desks.set(az.def.assignedAgentId, {
          x: az.def.x + az.def.width / 2,
          y: az.def.y + az.def.height / 2,
        });
      }
    }
    return desks;
  }

  destroy(): void {
    for (const az of this.zones) {
      az.zone.destroy();
      az.prompt.destroy();
    }
    this.zones = [];
    this.currentOverlap = null;
  }

  private createZone(def: InteractableDef): void {
    const zone = this.scene.add
      .zone(def.x + def.width / 2, def.y + def.height / 2, def.width, def.height)
      .setOrigin(0.5)
      .setDepth(1);

    // Visual indicator for the zone (subtle outline)
    const graphics = this.scene.add.graphics();
    graphics.lineStyle(1, 0x06b6d4, 0.3);
    graphics.strokeRect(def.x, def.y, def.width, def.height);
    graphics.setDepth(1);

    const promptLabel = def.interactType === 'silent-zone'
      ? ''
      : `[E] ${def.label ?? def.name}`;
    const prompt = this.scene.add
      .text(0, 0, promptLabel, {
        fontFamily: '"Press Start 2P", monospace',
        fontSize: '7px',
        color: '#22d3ee',
        backgroundColor: '#0f172aCC',
        padding: { x: 4, y: 2 },
      })
      .setOrigin(0.5)
      .setDepth(50)
      .setVisible(false);

    this.zones.push({ def, zone, prompt, isOverlapping: false });
  }

  private getProp(
    obj: Phaser.Types.Tilemaps.TiledObject,
    name: string,
  ): string | number | boolean | undefined {
    const props = obj.properties as
      | Array<{ name: string; value: string | number | boolean }>
      | undefined;
    if (!props) return undefined;
    const found = props.find((p) => p.name === name);
    return found?.value;
  }
}
