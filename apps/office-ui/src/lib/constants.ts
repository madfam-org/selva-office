/**
 * Shared UI-layer constants.
 *
 * Hook-level and component-level magic numbers and event name strings that
 * appear in multiple files are centralised here.
 */

/** Maximum delay between WebSocket reconnection attempts (ms). */
export const MAX_RECONNECT_DELAY_MS = 30000;

/** GameEventBus event key: suppresses game input while a text field has focus. */
export const EVENT_CHAT_FOCUS = 'chat-focus';

/** GameEventBus event key: suppresses game input while the emote picker is open. */
export const EVENT_EMOTE_PICKER_FOCUS = 'emote-picker-focus';
