'use client';

import { useCallback, useEffect, useState } from 'react';

import { apiFetch } from '@/lib/api';

export type VoiceMode = 'user_direct' | 'dyad_selva_plus_user' | 'agent_identified';

export interface VoiceModePreview {
  mode: VoiceMode;
  label: string;
  typed_phrase: string;
  heads_up: string;
  clause_body: string;
  clause_version: string;
}

export interface OnboardingStatus {
  voice_mode: VoiceMode | null;
  onboarding_complete: boolean;
  clause_version: string;
}

export function useVoiceMode() {
  const [status, setStatus] = useState<OnboardingStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await apiFetch('/api/v1/onboarding/status');
      if (!resp.ok) {
        throw new Error(`status ${resp.status}`);
      }
      const data = (await resp.json()) as OnboardingStatus;
      setStatus(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'unknown');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const loadPreview = useCallback(async (mode: VoiceMode): Promise<VoiceModePreview> => {
    const resp = await apiFetch(`/api/v1/onboarding/voice-mode/preview/${mode}`);
    if (!resp.ok) {
      throw new Error(`preview ${resp.status}`);
    }
    return (await resp.json()) as VoiceModePreview;
  }, []);

  const selectMode = useCallback(
    async (mode: VoiceMode, typedConfirmation: string): Promise<OnboardingStatus> => {
      const resp = await apiFetch('/api/v1/onboarding/voice-mode', {
        method: 'POST',
        body: JSON.stringify({ mode, typed_confirmation: typedConfirmation }),
      });
      if (!resp.ok) {
        const body = await resp.text();
        throw new Error(body || `select failed: ${resp.status}`);
      }
      const data = (await resp.json()) as OnboardingStatus;
      setStatus(data);
      return data;
    },
    [],
  );

  const changeMode = useCallback(
    async (mode: VoiceMode, typedConfirmation: string): Promise<OnboardingStatus> => {
      const resp = await apiFetch('/api/v1/settings/outbound-voice', {
        method: 'PUT',
        body: JSON.stringify({ mode, typed_confirmation: typedConfirmation }),
      });
      if (!resp.ok) {
        const body = await resp.text();
        throw new Error(body || `change failed: ${resp.status}`);
      }
      const data = (await resp.json()) as OnboardingStatus;
      setStatus(data);
      return data;
    },
    [],
  );

  return { status, loading, error, refresh, loadPreview, selectMode, changeMode };
}
