'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import type SimplePeerType from 'simple-peer';
import type { ProximityUpdate, WebRTCSignal } from './useColyseus';
import { useProximityVideoLiveKit } from './useProximityVideoLiveKit';
import { logger } from '../lib/logger';

interface PeerConnection {
  sessionId: string;
  peer: SimplePeerType.Instance;
  stream: MediaStream | null;
}

export interface ProximityPeer {
  sessionId: string;
  stream: MediaStream | null;
}

export interface LiveKitCredentials {
  url: string;
  token: string;
}

interface ProximityVideoOptions {
  localSessionId: string | null;
  sendSignal: (targetSessionId: string, signal: unknown) => void;
  enabled: boolean;
  playerStatus?: string;
  /** LiveKit credentials set by useColyseus when the server sends them. */
  liveKitCredentials?: LiveKitCredentials | null;
}

export type ScreenShareQuality = 'auto' | '720p' | '1080p';

export interface ProximityVideoState {
  peers: ProximityPeer[];
  localStream: MediaStream | null;
  audioEnabled: boolean;
  videoEnabled: boolean;
  screenSharing: boolean;
  noiseSuppression: boolean;
  screenShareQuality: ScreenShareQuality;
  setScreenShareQuality: (quality: ScreenShareQuality) => void;
  toggleAudio: () => void;
  toggleVideo: () => void;
  toggleScreenShare: () => void;
  toggleNoiseSuppression: () => void;
  /** Call when receiving a proximity_players message from the server */
  handleProximityUpdate: (update: ProximityUpdate) => void;
  /** Call when receiving a webrtc_signal message from the server */
  handleWebRTCSignal: (signal: WebRTCSignal) => void;
}

function buildIceServers(): RTCIceServer[] {
  const servers: RTCIceServer[] = [
    { urls: 'stun:stun.l.google.com:19302' },
    { urls: 'stun:stun1.l.google.com:19302' },
  ];

  // Add TURN server if configured
  const turnUrl = process.env.NEXT_PUBLIC_TURN_URL;
  if (turnUrl) {
    servers.push({
      urls: turnUrl,
      username: process.env.NEXT_PUBLIC_TURN_USERNAME ?? '',
      credential: process.env.NEXT_PUBLIC_TURN_CREDENTIAL ?? '',
    });
  }

  return servers;
}

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
  playerStatus,
  liveKitCredentials,
}: ProximityVideoOptions): ProximityVideoState {
  const [p2pPeers, setP2pPeers] = useState<ProximityPeer[]>([]);
  const [localStream, setLocalStream] = useState<MediaStream | null>(null);
  const [audioEnabled, setAudioEnabled] = useState(true);
  const [videoEnabled, setVideoEnabled] = useState(true);
  const [screenSharing, setScreenSharing] = useState(false);
  const [noiseSuppression, setNoiseSuppression] = useState(false);
  const [screenShareQuality, setScreenShareQuality] = useState<ScreenShareQuality>('auto');
  const [proximityMode, setProximityMode] = useState<'p2p' | 'sfu'>('p2p');
  const [nearbySessionIds, setNearbySessionIds] = useState<string[]>([]);

  const connectionsRef = useRef<Map<string, PeerConnection>>(new Map());
  const screenStreamRef = useRef<MediaStream | null>(null);
  const screenAudioCtxRef = useRef<AudioContext | null>(null);
  const noiseFilterRef = useRef<{ outputStream: MediaStream; context: AudioContext; destroy: () => void } | null>(null);
  const rawAudioTrackRef = useRef<MediaStreamTrack | null>(null);
  const errorTrackerRef = useRef<Map<string, { count: number; lastError: number; backoffUntil: number }>>(new Map());
  const localStreamRef = useRef<MediaStream | null>(null);
  const localSessionIdRef = useRef(localSessionId);
  localSessionIdRef.current = localSessionId;
  const sendSignalRef = useRef(sendSignal);
  sendSignalRef.current = sendSignal;
  const playerStatusRef = useRef(playerStatus);
  playerStatusRef.current = playerStatus;
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
        logger.warn('[useProximityVideo] getUserMedia failed:', err);
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
    setP2pPeers(peerList);
  }, []);

  const destroyPeer = useCallback((sessionId: string) => {
    const connection = connectionsRef.current.get(sessionId);
    if (connection) {
      connection.peer.destroy();
      connectionsRef.current.delete(sessionId);
      errorTrackerRef.current.delete(sessionId);
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
        config: { iceServers: buildIceServers() },
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
        const now = Date.now();
        const tracker = errorTrackerRef.current.get(remoteSessionId) ?? { count: 0, lastError: 0, backoffUntil: 0 };

        // Reset counter if last error was >30s ago
        if (now - tracker.lastError > 30_000) {
          tracker.count = 0;
        }

        tracker.count++;
        tracker.lastError = now;
        errorTrackerRef.current.set(remoteSessionId, tracker);

        if (tracker.count === 1) {
          // Only warn on first error per peer per 30s window
          logger.warn(`[useProximityVideo] Peer error with ${remoteSessionId}:`, err.message);
        }

        if (tracker.count >= 3) {
          // Too many errors — destroy and set exponential backoff
          const backoffMs = Math.min(30_000, 2_000 * Math.pow(2, tracker.count - 3));
          tracker.backoffUntil = now + backoffMs;
          errorTrackerRef.current.set(remoteSessionId, tracker);
          destroyPeer(remoteSessionId);
          // Re-add tracker after destroyPeer cleared it
          errorTrackerRef.current.set(remoteSessionId, tracker);
        }
        // count < 3: let ICE retry naturally, don't destroy
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

      // Read transport mode from server (defaults to p2p for backward compat)
      const mode = (update as ProximityUpdate & { mode?: 'p2p' | 'sfu' }).mode ?? 'p2p';
      setProximityMode(mode);

      // DND status suppresses all proximity connections
      const effectiveNearby = playerStatusRef.current === 'dnd' ? [] : update.nearbySessionIds;

      // Always track nearby IDs for LiveKit subscription management
      setNearbySessionIds(effectiveNearby);

      // When in SFU mode, skip simple-peer connection management entirely.
      // The LiveKit hook handles subscriptions based on nearbySessionIds.
      if (mode === 'sfu') {
        // Tear down any existing P2P connections when switching to SFU
        connectionsRef.current.forEach((conn) => conn.peer.destroy());
        connectionsRef.current.clear();
        updatePeersState();
        return;
      }

      const currentPeerIds = new Set(connectionsRef.current.keys());
      const nearbySet = new Set(effectiveNearby);

      // Create connections for new nearby players
      const now = Date.now();
      for (const remoteSid of effectiveNearby) {
        if (!currentPeerIds.has(remoteSid)) {
          // Check backoff from prior errors
          const tracker = errorTrackerRef.current.get(remoteSid);
          if (tracker && tracker.backoffUntil > now) {
            continue; // Still in backoff period
          }
          // Clear stale tracker if backoff expired
          if (tracker && tracker.backoffUntil <= now) {
            errorTrackerRef.current.delete(remoteSid);
          }
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

  // Cleanup all peers, screen share, and noise filter on unmount
  useEffect(() => {
    return () => {
      connectionsRef.current.forEach((conn) => conn.peer.destroy());
      connectionsRef.current.clear();
      errorTrackerRef.current.clear();
      screenStreamRef.current?.getTracks().forEach((t) => t.stop());
      screenStreamRef.current = null;
      if (screenAudioCtxRef.current) {
        screenAudioCtxRef.current.close().catch(() => {});
        screenAudioCtxRef.current = null;
      }
      if (noiseFilterRef.current) {
        noiseFilterRef.current.destroy();
        noiseFilterRef.current = null;
      }
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

  const restoreCameraTrack = useCallback(() => {
    const cameraTrack = localStreamRef.current?.getVideoTracks()[0];
    if (cameraTrack) {
      connectionsRef.current.forEach((conn) => {
        const sender = (conn.peer as unknown as { _pc?: RTCPeerConnection })._pc
          ?.getSenders?.()
          ?.find((s: RTCRtpSender) => s.track?.kind === 'video');
        if (sender) {
          sender.replaceTrack(cameraTrack).catch(() => {});
        }
      });
    }
  }, []);

  const stopScreenAudioCtx = useCallback(() => {
    if (screenAudioCtxRef.current) {
      screenAudioCtxRef.current.close().catch(() => {});
      screenAudioCtxRef.current = null;
    }
  }, []);

  const restoreMicAudioTrack = useCallback(() => {
    const micTrack = localStreamRef.current?.getAudioTracks()[0];
    if (micTrack) {
      connectionsRef.current.forEach((conn) => {
        const sender = (conn.peer as unknown as { _pc?: RTCPeerConnection })._pc
          ?.getSenders?.()
          ?.find((s: RTCRtpSender) => s.track?.kind === 'audio');
        if (sender) {
          sender.replaceTrack(micTrack).catch(() => {});
        }
      });
    }
  }, []);

  const toggleScreenShare = useCallback(async () => {
    if (screenSharing) {
      // Stop screen share -- restore camera track and mic audio
      screenStreamRef.current?.getTracks().forEach((t) => t.stop());
      screenStreamRef.current = null;
      stopScreenAudioCtx();
      setScreenSharing(false);
      restoreCameraTrack();
      restoreMicAudioTrack();
      return;
    }

    try {
      // Build video constraints based on quality preset
      // 'cursor' is a valid getDisplayMedia constraint but not in MediaTrackConstraints typedef
      let videoConstraints: Record<string, unknown> = { cursor: 'always' };
      if (screenShareQuality === '720p') {
        videoConstraints = { cursor: 'always', width: { ideal: 1280 }, height: { ideal: 720 } };
      } else if (screenShareQuality === '1080p') {
        videoConstraints = { cursor: 'always', width: { ideal: 1920 }, height: { ideal: 1080 } };
      }

      const screenStream = await navigator.mediaDevices.getDisplayMedia({
        video: videoConstraints as MediaTrackConstraints,
        audio: true,
      });
      screenStreamRef.current = screenStream;
      setScreenSharing(true);

      const screenTrack = screenStream.getVideoTracks()[0];

      // Auto-stop when user ends share via browser UI
      screenTrack.onended = () => {
        screenStreamRef.current?.getTracks().forEach((t) => t.stop());
        screenStreamRef.current = null;
        stopScreenAudioCtx();
        setScreenSharing(false);
        restoreCameraTrack();
        restoreMicAudioTrack();
      };

      // Replace video track on all existing peers
      connectionsRef.current.forEach((conn) => {
        const sender = (conn.peer as unknown as { _pc?: RTCPeerConnection })._pc
          ?.getSenders?.()
          ?.find((s: RTCRtpSender) => s.track?.kind === 'video');
        if (sender) {
          sender.replaceTrack(screenTrack).catch(() => {});
        }
      });

      // Mix system audio with mic audio if the browser provided an audio track
      const screenAudioTrack = screenStream.getAudioTracks()[0];
      if (screenAudioTrack) {
        const micTrack = localStreamRef.current?.getAudioTracks()[0];
        if (micTrack) {
          // Mix both audio sources into a single track via AudioContext
          const ctx = new AudioContext();
          screenAudioCtxRef.current = ctx;
          const dest = ctx.createMediaStreamDestination();
          const screenSource = ctx.createMediaStreamSource(new MediaStream([screenAudioTrack]));
          const micSource = ctx.createMediaStreamSource(new MediaStream([micTrack]));
          screenSource.connect(dest);
          micSource.connect(dest);
          const mixedTrack = dest.stream.getAudioTracks()[0];

          // Replace audio track on all peers with the mixed track
          connectionsRef.current.forEach((conn) => {
            const sender = (conn.peer as unknown as { _pc?: RTCPeerConnection })._pc
              ?.getSenders?.()
              ?.find((s: RTCRtpSender) => s.track?.kind === 'audio');
            if (sender) {
              sender.replaceTrack(mixedTrack).catch(() => {});
            }
          });
        } else {
          // No mic -- send system audio only
          connectionsRef.current.forEach((conn) => {
            const sender = (conn.peer as unknown as { _pc?: RTCPeerConnection })._pc
              ?.getSenders?.()
              ?.find((s: RTCRtpSender) => s.track?.kind === 'audio');
            if (sender) {
              sender.replaceTrack(screenAudioTrack).catch(() => {});
            }
          });
        }
      }
    } catch (err) {
      logger.warn('[useProximityVideo] getDisplayMedia failed:', err);
    }
  }, [screenSharing, screenShareQuality, restoreCameraTrack, restoreMicAudioTrack, stopScreenAudioCtx]);

  const toggleNoiseSuppression = useCallback(async () => {
    const stream = localStreamRef.current;
    if (!stream) return;

    if (noiseSuppression) {
      // Disable: restore raw audio track
      if (noiseFilterRef.current) {
        noiseFilterRef.current.destroy();
        noiseFilterRef.current = null;
      }
      if (rawAudioTrackRef.current) {
        // Replace filtered track with raw track on all peers
        connectionsRef.current.forEach((conn) => {
          const sender = (conn.peer as unknown as { _pc?: RTCPeerConnection })._pc
            ?.getSenders?.()
            ?.find((s: RTCRtpSender) => s.track?.kind === 'audio');
          if (sender) {
            sender.replaceTrack(rawAudioTrackRef.current).catch(() => {});
          }
        });
      }
      setNoiseSuppression(false);
      return;
    }

    // Enable: create filter chain and replace audio track
    const { createNoiseFilter } = await import('./audio-processor');
    const filter = createNoiseFilter(stream);
    if (!filter) return;

    noiseFilterRef.current = filter;
    rawAudioTrackRef.current = stream.getAudioTracks()[0] ?? null;

    const filteredTrack = filter.outputStream.getAudioTracks()[0];
    if (filteredTrack) {
      connectionsRef.current.forEach((conn) => {
        const sender = (conn.peer as unknown as { _pc?: RTCPeerConnection })._pc
          ?.getSenders?.()
          ?.find((s: RTCRtpSender) => s.track?.kind === 'audio');
        if (sender) {
          sender.replaceTrack(filteredTrack).catch(() => {});
        }
      });
    }
    setNoiseSuppression(true);
  }, [noiseSuppression]);

  // ── LiveKit SFU hook (conditional on credentials + mode) ──────────
  const sfuActive = proximityMode === 'sfu' && !!liveKitCredentials;
  const { peers: sfuPeers } = useProximityVideoLiveKit({
    url: sfuActive ? liveKitCredentials!.url : '',
    token: sfuActive ? liveKitCredentials!.token : '',
    nearbySessionIds: sfuActive ? nearbySessionIds : [],
    audioEnabled,
    videoEnabled,
  });

  // Select peers from the active transport
  const peers = sfuActive ? sfuPeers : p2pPeers;

  return {
    peers,
    localStream,
    audioEnabled,
    videoEnabled,
    screenSharing,
    noiseSuppression,
    screenShareQuality,
    setScreenShareQuality,
    toggleAudio,
    toggleVideo,
    toggleScreenShare,
    toggleNoiseSuppression,
    handleProximityUpdate,
    handleWebRTCSignal,
  };
}
