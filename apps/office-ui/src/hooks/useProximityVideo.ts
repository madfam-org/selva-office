'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import type SimplePeerType from 'simple-peer';
import type { ProximityUpdate, WebRTCSignal } from './useColyseus';

interface PeerConnection {
  sessionId: string;
  peer: SimplePeerType.Instance;
  stream: MediaStream | null;
}

export interface ProximityPeer {
  sessionId: string;
  stream: MediaStream | null;
}

interface ProximityVideoOptions {
  localSessionId: string | null;
  sendSignal: (targetSessionId: string, signal: unknown) => void;
  enabled: boolean;
}

export interface ProximityVideoState {
  peers: ProximityPeer[];
  localStream: MediaStream | null;
  audioEnabled: boolean;
  videoEnabled: boolean;
  toggleAudio: () => void;
  toggleVideo: () => void;
  /** Call when receiving a proximity_players message from the server */
  handleProximityUpdate: (update: ProximityUpdate) => void;
  /** Call when receiving a webrtc_signal message from the server */
  handleWebRTCSignal: (signal: WebRTCSignal) => void;
}

const STUN_SERVERS = [
  { urls: 'stun:stun.l.google.com:19302' },
  { urls: 'stun:stun1.l.google.com:19302' },
];

/**
 * Manages WebRTC peer connections for proximity-based video/audio.
 * Uses simple-peer for WebRTC. Signal relay is handled by the caller
 * via sendSignal callback and handleWebRTCSignal/handleProximityUpdate
 * imperative methods.
 *
 * The client with the lexicographically lower sessionId initiates offers
 * (deterministic, avoids race conditions).
 */
export function useProximityVideo({
  localSessionId,
  sendSignal,
  enabled,
}: ProximityVideoOptions): ProximityVideoState {
  const [peers, setPeers] = useState<ProximityPeer[]>([]);
  const [localStream, setLocalStream] = useState<MediaStream | null>(null);
  const [audioEnabled, setAudioEnabled] = useState(true);
  const [videoEnabled, setVideoEnabled] = useState(true);

  const connectionsRef = useRef<Map<string, PeerConnection>>(new Map());
  const localStreamRef = useRef<MediaStream | null>(null);
  const localSessionIdRef = useRef(localSessionId);
  localSessionIdRef.current = localSessionId;
  const sendSignalRef = useRef(sendSignal);
  sendSignalRef.current = sendSignal;
  const SimplePeerRef = useRef<typeof SimplePeerType | null>(null);

  // Lazy-load simple-peer
  useEffect(() => {
    if (!enabled) return;
    import('simple-peer').then((mod) => {
      SimplePeerRef.current = mod.default;
    });
  }, [enabled]);

  // Acquire local media stream
  useEffect(() => {
    if (!enabled) return;

    let cancelled = false;

    navigator.mediaDevices
      .getUserMedia({ audio: true, video: { width: 128, height: 128 } })
      .then((stream) => {
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        localStreamRef.current = stream;
        setLocalStream(stream);
      })
      .catch((err) => {
        console.warn('[useProximityVideo] getUserMedia failed:', err);
      });

    return () => {
      cancelled = true;
      localStreamRef.current?.getTracks().forEach((t) => t.stop());
      localStreamRef.current = null;
      setLocalStream(null);
    };
  }, [enabled]);

  const updatePeersState = useCallback(() => {
    const peerList: ProximityPeer[] = [];
    connectionsRef.current.forEach((conn) => {
      peerList.push({
        sessionId: conn.sessionId,
        stream: conn.stream,
      });
    });
    setPeers(peerList);
  }, []);

  const destroyPeer = useCallback((sessionId: string) => {
    const connection = connectionsRef.current.get(sessionId);
    if (connection) {
      connection.peer.destroy();
      connectionsRef.current.delete(sessionId);
      updatePeersState();
    }
  }, [updatePeersState]);

  const createPeer = useCallback(
    (
      remoteSessionId: string,
      initiator: boolean,
      incomingSignal?: SimplePeerType.SignalData,
    ) => {
      const SimplePeer = SimplePeerRef.current;
      if (!SimplePeer || !localStreamRef.current) return;

      // Prevent duplicate connections
      if (connectionsRef.current.has(remoteSessionId)) return;

      const peer = new SimplePeer({
        initiator,
        stream: localStreamRef.current,
        trickle: true,
        config: { iceServers: STUN_SERVERS },
      });

      const connection: PeerConnection = {
        sessionId: remoteSessionId,
        peer,
        stream: null,
      };
      connectionsRef.current.set(remoteSessionId, connection);

      peer.on('signal', (signal: SimplePeerType.SignalData) => {
        sendSignalRef.current(remoteSessionId, signal);
      });

      peer.on('stream', (remoteStream: MediaStream) => {
        connection.stream = remoteStream;
        updatePeersState();
      });

      peer.on('close', () => {
        destroyPeer(remoteSessionId);
      });

      peer.on('error', (err: Error) => {
        console.warn(`[useProximityVideo] Peer error with ${remoteSessionId}:`, err.message);
        destroyPeer(remoteSessionId);
      });

      if (incomingSignal) {
        peer.signal(incomingSignal);
      }

      updatePeersState();
    },
    [updatePeersState, destroyPeer],
  );

  // Imperative handler for proximity updates (called by useColyseus callback)
  const handleProximityUpdate = useCallback(
    (update: ProximityUpdate) => {
      const sid = localSessionIdRef.current;
      if (!sid) return;

      const currentPeerIds = new Set(connectionsRef.current.keys());
      const nearbySet = new Set(update.nearbySessionIds);

      // Create connections for new nearby players
      for (const remoteSid of update.nearbySessionIds) {
        if (!currentPeerIds.has(remoteSid)) {
          // Only initiate if our sessionId is lexicographically lower
          if (sid < remoteSid) {
            createPeer(remoteSid, true);
          }
        }
      }

      // Destroy connections for players no longer nearby
      for (const remoteSid of currentPeerIds) {
        if (!nearbySet.has(remoteSid)) {
          destroyPeer(remoteSid);
        }
      }
    },
    [createPeer, destroyPeer],
  );

  // Imperative handler for WebRTC signals (called by useColyseus callback)
  const handleWebRTCSignal = useCallback(
    (signal: WebRTCSignal) => {
      const existing = connectionsRef.current.get(signal.fromSessionId);
      if (existing) {
        existing.peer.signal(signal.signal as SimplePeerType.SignalData);
      } else {
        // Incoming connection — we are the non-initiator
        createPeer(
          signal.fromSessionId,
          false,
          signal.signal as SimplePeerType.SignalData,
        );
      }
    },
    [createPeer],
  );

  // Cleanup all peers on unmount
  useEffect(() => {
    return () => {
      connectionsRef.current.forEach((conn) => conn.peer.destroy());
      connectionsRef.current.clear();
    };
  }, []);

  const toggleAudio = useCallback(() => {
    localStreamRef.current?.getAudioTracks().forEach((t) => {
      t.enabled = !t.enabled;
    });
    setAudioEnabled((prev) => !prev);
  }, []);

  const toggleVideo = useCallback(() => {
    localStreamRef.current?.getVideoTracks().forEach((t) => {
      t.enabled = !t.enabled;
    });
    setVideoEnabled((prev) => !prev);
  }, []);

  return {
    peers,
    localStream,
    audioEnabled,
    videoEnabled,
    toggleAudio,
    toggleVideo,
    handleProximityUpdate,
    handleWebRTCSignal,
  };
}
