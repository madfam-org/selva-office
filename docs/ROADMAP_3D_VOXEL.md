# 3D Voxel Office — Next-Gen UI Roadmap

## Vision

Translate the current 2D pixel-art solarpunk office into a **3D voxel workspace** with isometric/free-camera navigation, maintaining the same game loop (agents, tasks, approvals, chat) but with immersive depth. Visual reference: [3D Office Pack (Unity)](https://assetstore.unity.com/packages/3d/environments/3d-office-pack-modular-291704) — modular furniture, warm lighting, realistic office layout.

The 3D view operates as a **"Game View" toggle** alongside the existing 2D view and the Simple (accessible HTML) view — not a replacement. Users choose their preferred experience.

## Architecture

### Current (2D)
```
Phaser 3 (Canvas/WebGL) → 32x32 pixel sprites → TiledMapLoader (.tmj)
                        → Colyseus state sync  → React overlay panels
```

### Target (3D)
```
Three.js / React Three Fiber → Voxel models (MagicaVoxel .vox / glTF)
                             → Same Colyseus state sync
                             → Same React overlay panels (HUD, Ops Feed, Dashboard)
```

### Key Principle: Shared State, Different Renderers

The 3D view DOES NOT replace the backend or state management. It is a new **renderer** consuming the same:
- Colyseus `OfficeStateSchema` (agents, players, approvals, chat)
- React state (tasks, events, metrics)
- GameEventBus (inter-component communication)

The switch is at the rendering layer only.

## Implementation Phases

### Phase 1: Voxel Asset Pipeline
- **Tool**: MagicaVoxel (free) or Kenney Voxel Pack
- **Assets needed**:
  - 4 department rooms (Engineering greenhouse, Library garden, Market garden, Zen garden)
  - Modular furniture: desks, chairs, monitors, plants, bookshelves, server racks
  - Agent characters: 10 voxel avatars matching the solarpunk aesthetic
  - Ambient: light fixtures, windows, floor tiles, wall segments
- **Format**: Export as `.glb` (glTF binary) for Three.js consumption
- **Budget**: ~50 unique models, <2MB total (voxel geometry is inherently compact)

### Phase 2: 3D Scene Component
- **File**: `apps/office-ui/src/game/VoxelOfficeScene.tsx`
- **Framework**: React Three Fiber + @react-three/drei
- **Layout**: Convert the 50x28 tile grid to a 3D grid (1 tile = 1 unit)
- **Camera**: Isometric default with free-orbit option
- **Lighting**: Warm ambient + per-department colored point lights (matching 2D biome tints)
- **Agent rendering**: Voxel character models with idle bob, walking, working animations

### Phase 3: State Bridge
- **File**: `apps/office-ui/src/game/VoxelStateBridge.ts`
- Map Colyseus `TacticianSchema` position (x, y) → 3D world position (x, 0, z)
- Map agent status → 3D visual effects (idle glow, working particle, error pulse)
- Map department zones → 3D room boundaries
- Interactable zones → 3D clickable objects (dispatch stations, review stations)

### Phase 4: View Toggle
- **File**: `apps/office-ui/src/app/office/page.tsx`
- Add a third view mode: `viewMode: 'game' | 'simple' | '3d'`
- Toggle button in HUD: `🎮 2D` / `🧊 3D` / `📄 Simple`
- Persist preference to localStorage
- Lazy-load the 3D renderer (`React.lazy()` + `Suspense`)

### Phase 5: Optimization
- Level-of-detail (LOD) for distant objects
- Instanced rendering for repeated furniture
- Frustum culling
- Progressive loading with skeleton placeholder
- Target: <3s first paint, 60fps on M1 MacBook

## Design Language

### Solarpunk Voxel Aesthetic
- **Palette**: Warm earth tones (wood #8b7355, bamboo #c8b896, moss #4a9e6e) — same as 2D
- **Materials**: Matte/unlit voxel look (no PBR — keeps the stylized feel)
- **Vegetation**: Low-poly plants, hanging vines, moss patches on walls
- **Lighting**: Golden hour warm tones, per-department accent colors
- **Scale**: Slightly exaggerated proportions (chunky furniture, oversized plants)

### Department Biomes in 3D
| Department | 2D Theme | 3D Translation |
|-----------|---------|----------------|
| Engineering | Tech Greenhouse (blue) | Glass-walled greenhouse with server racks + hanging LED strips |
| Research | Library Garden (teal) | Bookshelf walls, reading nooks, floating hologram displays |
| Growth | Market Garden (purple) | Open plan with standing desks, whiteboard walls, plant dividers |
| Support | Zen Garden (green) | Low furniture, rock garden, water feature, meditation corner |

## Dependencies
- `@react-three/fiber` — React renderer for Three.js
- `@react-three/drei` — Helpers (OrbitControls, Environment, Instances)
- `three` — 3D engine
- Asset pipeline: MagicaVoxel → glTF export → hosted on CDN / public/assets/3d/

## Non-Goals (This Phase)
- VR/XR support (future consideration)
- Multiplayer avatar customization in 3D (reuse 2D config, render as voxel)
- Real-time shadows (performance cost too high for browser)
- Physics engine (not needed — movement is tile-grid based)

## Reference
- [3D Office Pack — Unity Asset Store](https://assetstore.unity.com/packages/3d/environments/3d-office-pack-modular-291704?aid=1011l37TN&pubref=2022_H_2)
- [MagicaVoxel](https://ephtracy.github.io/) — free voxel editor
- [Kenney Voxel Pack](https://kenney.nl/assets/voxel-pack) — CC0 voxel assets
- [React Three Fiber](https://docs.pmnd.rs/react-three-fiber) — React Three.js renderer
