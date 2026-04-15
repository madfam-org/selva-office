/**
 * Minimal type declarations for livekit-server-sdk.
 * The package is an optional dependency — dynamically imported at runtime.
 * These declarations allow TypeScript to compile without the package installed.
 */
declare module "livekit-server-sdk" {
  export interface VideoGrant {
    room?: string;
    roomJoin?: boolean;
    canPublish?: boolean;
    canSubscribe?: boolean;
  }

  export class AccessToken {
    constructor(
      apiKey: string,
      apiSecret: string,
      options?: { identity?: string; name?: string },
    );
    addGrant(grant: VideoGrant): void;
    ttl: string;
    toJwt(): Promise<string>;
  }
}
