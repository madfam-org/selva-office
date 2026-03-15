/** Guest access types shared between frontend and backend. */

export interface GuestTokenRequest {
  display_name?: string;
  org_id?: string;
  invite_token?: string;
  ttl_hours?: number;
}

export interface GuestTokenResponse {
  access_token: string;
  expires_at: string;
  guest_id: string;
  display_name: string;
  org_id: string;
}

export interface GuestInviteValidation {
  valid: boolean;
  org_name?: string;
  room_id?: string;
  expires_at?: string;
}
