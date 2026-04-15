/**
 * Minimal type declarations for livekit-client.
 * The package is an optional dependency — dynamically imported at runtime
 * only when SFU mode is active. These declarations allow TypeScript to
 * compile without the package installed.
 */
declare module "livekit-client" {
  export enum RoomEvent {
    TrackSubscribed = "trackSubscribed",
    TrackUnsubscribed = "trackUnsubscribed",
    ParticipantDisconnected = "participantDisconnected",
  }

  export interface TrackPublication {
    track: {
      kind: string;
      mediaStreamTrack: MediaStreamTrack;
    } | null;
    isSubscribed: boolean;
    setSubscribed(subscribed: boolean): void;
  }

  export interface RemoteParticipant {
    identity: string;
    trackPublications: Map<string, TrackPublication>;
  }

  export interface LocalParticipant {
    enableCameraAndMicrophone(): Promise<void>;
    setMicrophoneEnabled(enabled: boolean): Promise<void>;
    setCameraEnabled(enabled: boolean): Promise<void>;
  }

  export class Room {
    remoteParticipants: Map<string, RemoteParticipant>;
    localParticipant: LocalParticipant;
    on(event: RoomEvent, handler: (...args: unknown[]) => void): void;
    connect(url: string, token: string): Promise<void>;
    disconnect(): void;
  }
}
