import { renderHook, act, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useVoiceMode } from '../useVoiceMode';

describe('useVoiceMode', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('fetches onboarding status on mount', async () => {
    const status = {
      voice_mode: null,
      onboarding_complete: false,
      clause_version: 'voice-mode-v1.0',
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => status,
    });
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useVoiceMode());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.status).toEqual(status);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/onboarding/status'),
      expect.anything(),
    );
  });

  it('selectMode posts to /onboarding/voice-mode and updates status', async () => {
    const initialStatus = {
      voice_mode: null,
      onboarding_complete: false,
      clause_version: 'voice-mode-v1.0',
    };
    const finalStatus = {
      voice_mode: 'dyad_selva_plus_user',
      onboarding_complete: true,
      clause_version: 'voice-mode-v1.0',
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => initialStatus })
      .mockResolvedValueOnce({ ok: true, json: async () => finalStatus });
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useVoiceMode());
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.selectMode('dyad_selva_plus_user', 'I authorize…');
    });

    expect(result.current.status?.voice_mode).toBe('dyad_selva_plus_user');
    const selectCall = fetchMock.mock.calls[1];
    expect(selectCall[0]).toContain('/api/v1/onboarding/voice-mode');
    expect(selectCall[1]).toMatchObject({ method: 'POST' });
  });

  it('changeMode PUTs to /settings/outbound-voice', async () => {
    const initialStatus = {
      voice_mode: 'dyad_selva_plus_user',
      onboarding_complete: true,
      clause_version: 'voice-mode-v1.0',
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => initialStatus })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ ...initialStatus, voice_mode: 'agent_identified' }),
      });
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useVoiceMode());
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.changeMode('agent_identified', 'I authorize…');
    });

    const changeCall = fetchMock.mock.calls[1];
    expect(changeCall[0]).toContain('/api/v1/settings/outbound-voice');
    expect(changeCall[1]).toMatchObject({ method: 'PUT' });
    expect(result.current.status?.voice_mode).toBe('agent_identified');
  });
});
