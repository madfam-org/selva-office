'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import type { ProximityPeer } from './useProximityVideo';
import { logger } from '../lib/logger';

interface LiveKitOptions {
  /** LiveKit server WebSocket URL. */
  url: string;
  /** Signed access token for the participant. */
  token: string;
  /** Session IDs of players currently within proximity range. */
  nearbySessionIds: string[];
  /** Whether local audio should be published. */
  audioEnabled: boolean;
  /** Whether local video should be published. */
  videoEnabled: boolean;
}

/**
 * Hook that connects to a LiveKit SFU room and manages track subscriptions
 * based on proximity. Returns the same `ProximityPeer[]` shape as the
 * simple-peer hook so the two are interchangeable from the caller's
 * perspective.
 *
 * `livekit-client` is dynamically imported so the bundle only includes
 * the SDK when SFU mode is actually used.
 */
export function useProximityVideoLiveKit(options: LiveKitOptions) {
  const { url, token, nearbySessionIds, audioEnabled, videoEnabled } = options;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const roomRef = useRef<any>(null);
  const [peers, setPeers] = useState<ProximityPeer[]>([]);
  const [connected, setConnected] = useState(false);

  // Keep a stable ref for the updatePeers helper so event handlers
  // always reference the latest room without re-registering listeners.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const updatePeers = useCallback((room: any) => {
    if (!room) return;
    const newPeers: ProximityPeer[] = [];
    for (const p of room.remoteParticipants.values()) {
      const pubs = Array.from(
        p.trackPublications.values(),
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ) as any[];

      const videoTrack = pubs.find(
        (pub) => pub.track?.kind === 'video' && pub.isSubscribed,
      );
      const audioTrack = pubs.find(
        (pub) => pub.track?.kind === 'audio' && pub.isSubscribed,
      );

      let stream: MediaStream | null = null;
      if (videoTrack?.track || audioTrack?.track) {
        stream = new MediaStream();
        if (videoTrack?.track?.mediaStreamTrack) {
          stream.addTrack(videoTrack.track.mediaStreamTrack);
        }
        if (audioTrack?.track?.mediaStreamTrack) {
          stream.addTrack(audioTrack.track.mediaStreamTrack);
        }
      }
      newPeers.push({ sessionId: p.identity, stream });
    }
    setPeers(newPeers);
  }, []);

  // ── Connect / disconnect lifecycle ──────────────────────────────────
  useEffect(() => {
    if (!url || !token) return;
    let cancelled = false;

    (async () => {
      try {
        const { Room, RoomEvent } = await import('livekit-client');
        const room = new Room();
        roomRef.current = room;

        room.on(RoomEvent.TrackSubscribed, () => {
          if (!cancelled) updatePeers(room);
        });
        room.on(RoomEvent.TrackUnsubscribed, () => {
          if (!cancelled) updatePeers(room);
        });
        room.on(RoomEvent.ParticipantDisconnected, () => {
          if (!cancelled) updatePeers(room);
        });

        await room.connect(url, token);
        if (cancelled) {
          room.disconnect();
          return;
        }
        setConnected(true);

        // Publish local tracks
        await room.localParticipant.enableCameraAndMicrophone();
        if (!audioEnabled) {
          await room.localParticipant.setMicrophoneEnabled(false);
        }
        if (!videoEnabled) {
          await room.localParticipant.setCameraEnabled(false);
        }
      } catch (err) {
        logger.debug('[LiveKit] Connection failed:', err);
      }
    })();

    return () => {
      cancelled = true;
      roomRef.current?.disconnect();
      roomRef.current = null;
      setConnected(false);
      setPeers([]);
    };
    // We intentionally depend only on url and token — reconnect when
    // credentials change, not on every audioEnabled/videoEnabled toggle.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, token]);

  // ── Toggle local audio/video tracks without reconnecting ───────────
  useEffect(() => {
    const room = roomRef.current;
    if (!room || !connected) return;
    room.localParticipant.setMicrophoneEnabled(audioEnabled).catch(() => {});
  }, [audioEnabled, connected]);

  useEffect(() => {
    const room = roomRef.current;
    if (!room || !connected) return;
    room.localParticipant.setCameraEnabled(videoEnabled).catch(() => {});
  }, [videoEnabled, connected]);

  // ── Proximity-based subscription management ────────────────────────
  useEffect(() => {
    const room = roomRef.current;
    if (!room || !connected) return;

    const nearbySet = new Set(nearbySessionIds);

    for (const participant of room.remoteParticipants.values()) {
      const isNearby = nearbySet.has(participant.identity);
      for (const pub of participant.trackPublications.values()) {
        if (pub.track) {
          pub.setSubscribed(isNearby);
        }
      }
    }
    updatePeers(room);
  }, [nearbySessionIds, connected, updatePeers]);

  return { peers, connected };
}
