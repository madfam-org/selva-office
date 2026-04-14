/**
 * Centralized game constants.
 *
 * All simple numeric/string magic numbers used across the game layer live here
 * so every module references a single source of truth.
 */

// === Layout ===
export const TILE_SIZE = 32;
export const WORLD_COLS = 50;
export const WORLD_ROWS = 28;

// === Movement & Interaction ===
export const TACTICIAN_SPEED = 200;       // px/s player movement
export const PROXIMITY_THRESHOLD = 64;    // px for interactable detection
export const MOVE_THROTTLE_MS = 66;       // ~15fps network send rate

// === Timing (ms) ===
export const EMOTE_DURATION_MS = 3000;
export const ANIM_FADE_MS = 800;          // standard fade/tween duration
export const DUST_MOTE_INTERVAL_MS = 800; // ambient particle spawn rate
export const STATUS_PARTICLE_INTERVAL_MS = 2000;

// === Spawn Grid ===
export const SPAWN_OFFSET = 48;           // px offset from zone edge for agent placement
export const SPAWN_GRID_SPACING = 48;     // px between agent spawn positions

// === Visual ===
export const HALO_RADIUS = 14;            // px radius for agent status halo
export const HALO_Y_OFFSET = 4;           // px below sprite center
export const EMOTE_Y_OFFSET = -32;        // px above sprite for emote bubbles

// === Agent Behavior ===
export const AGENT_SPEED = 30;            // px/s slow patrol
export const WAYPOINT_INTERVAL_MIN = 3000; // ms
export const WAYPOINT_INTERVAL_MAX = 7000; // ms
export const ARRIVAL_THRESHOLD = 2;       // px

// === Virtual Joystick ===
export const JOYSTICK_BASE_RADIUS = 40;
export const JOYSTICK_THUMB_RADIUS = 16;
export const JOYSTICK_DEADZONE = 0.2;

// === Companion Behavior ===
export const COMPANION_SPEED = 180;       // slightly slower than player (200)
export const FOLLOW_DISTANCE = 28;        // px behind owner
export const LAG_FACTOR = 0.08;           // interpolation lag (lower = more delay)
