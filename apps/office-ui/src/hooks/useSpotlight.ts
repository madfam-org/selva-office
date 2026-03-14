'use client';

import { useState, useCallback } from 'react';

interface SpotlightActiveEvent {
  sessionId: string;
  name?: string;
  active: boolean;
}

interface UseSpotlightOptions {
  localSessionId: string | null;
  sendSpotlightStart: () => void;
  sendSpotlightStop: () => void;
  enabled: boolean;
}

export interface SpotlightState {
  /** Whether a spotlight presentation is currently active in the room */
  active: boolean;
  /** Whether the local player is the current presenter */
  isPresenting: boolean;
  /** The name of the current presenter, or null if none */
  presenterName: string | null;
  /** The sessionId of the current presenter, or null if none */
  presenterSessionId: string | null;
  /** Start a spotlight presentation */
  startSpotlight: () => void;
  /** Stop the current spotlight presentation */
  stopSpotlight: () => void;
  /** Handle spotlight_active broadcast from Colyseus */
  handleSpotlightActive: (event: SpotlightActiveEvent) => void;
}

export function useSpotlight({
  localSessionId,
  sendSpotlightStart,
  sendSpotlightStop,
  enabled,
}: UseSpotlightOptions): SpotlightState {
  const [active, setActive] = useState(false);
  const [presenterName, setPresenterName] = useState<string | null>(null);
  const [presenterSessionId, setPresenterSessionId] = useState<string | null>(null);

  const isPresenting = active && presenterSessionId === localSessionId;

  const startSpotlight = useCallback(() => {
    if (!enabled) return;
    sendSpotlightStart();
  }, [enabled, sendSpotlightStart]);

  const stopSpotlight = useCallback(() => {
    if (!enabled) return;
    sendSpotlightStop();
  }, [enabled, sendSpotlightStop]);

  const handleSpotlightActive = useCallback((event: SpotlightActiveEvent) => {
    if (event.active) {
      setActive(true);
      setPresenterName(event.name ?? null);
      setPresenterSessionId(event.sessionId);
    } else {
      setActive(false);
      setPresenterName(null);
      setPresenterSessionId(null);
    }
  }, []);

  return {
    active,
    isPresenting,
    presenterName,
    presenterSessionId,
    startSpotlight,
    stopSpotlight,
    handleSpotlightActive,
  };
}
