'use client';

import { useCallback, useEffect, useState } from 'react';

import { VoiceModePreview } from '@/components/VoiceModePreview';
import {
  type OnboardingStatus,
  type VoiceMode,
  type VoiceModePreview as PreviewData,
  useVoiceMode,
} from '@/hooks/useVoiceMode';

const MODE_LABELS: Record<VoiceMode, string> = {
  user_direct: 'Send as me (no AI disclosure)',
  dyad_selva_plus_user: 'Co-branded: Selva on behalf of me',
  agent_identified: 'Selva agent identifies itself',
};

interface Props {
  onDone: (status: OnboardingStatus) => void;
  mode: 'onboarding' | 'change';
}

export function VoiceModeStep({ onDone, mode: flowMode }: Props) {
  const { loadPreview, selectMode, changeMode } = useVoiceMode();
  const [selected, setSelected] = useState<VoiceMode>('dyad_selva_plus_user');
  const [preview, setPreview] = useState<PreviewData | null>(null);
  const [typed, setTyped] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);

  useEffect(() => {
    setPreview(null);
    setTyped('');
    setAcknowledged(false);
    setError(null);
    loadPreview(selected)
      .then(setPreview)
      .catch((err) => setError(err instanceof Error ? err.message : 'load failed'));
  }, [selected, loadPreview]);

  const canSubmit =
    preview !== null &&
    typed.trim().length > 0 &&
    typed.trim().toLowerCase() === preview.typed_phrase.toLowerCase() &&
    (selected !== 'user_direct' || acknowledged) &&
    !busy;

  const submit = useCallback(async () => {
    if (!preview) return;
    setBusy(true);
    setError(null);
    try {
      const fn = flowMode === 'onboarding' ? selectMode : changeMode;
      const status = await fn(selected, typed.trim());
      onDone(status);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'submission failed');
    } finally {
      setBusy(false);
    }
  }, [preview, flowMode, selectMode, changeMode, selected, typed, onDone]);

  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <label htmlFor="voice-mode-select" className="text-sm font-semibold text-slate-200">
          Choose your outbound voice
        </label>
        <select
          id="voice-mode-select"
          value={selected}
          onChange={(e) => setSelected(e.target.value as VoiceMode)}
          className="w-full rounded border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-100"
          disabled={busy}
        >
          {(Object.keys(MODE_LABELS) as VoiceMode[]).map((m) => (
            <option key={m} value={m}>
              {MODE_LABELS[m]}
            </option>
          ))}
        </select>
      </div>

      {preview && <VoiceModePreview preview={preview} />}

      {selected === 'user_direct' && (
        <label className="flex items-start gap-2 rounded border border-amber-600/60 bg-amber-950/40 p-3 text-xs text-amber-200">
          <input
            type="checkbox"
            checked={acknowledged}
            onChange={(e) => setAcknowledged(e.target.checked)}
            className="mt-1"
            disabled={busy}
          />
          <span>
            I understand that no AI disclosure will be added and that I am responsible for
            compliance with applicable laws for my recipients (including California SB-1001 and
            Canadian CASL).
          </span>
        </label>
      )}

      {preview && (
        <div className="space-y-2">
          <label htmlFor="voice-typed" className="text-xs font-semibold text-slate-300">
            Type the phrase below to confirm
          </label>
          <p className="rounded bg-slate-800/60 p-2 font-mono text-xs text-slate-300">
            {preview.typed_phrase}
          </p>
          <input
            id="voice-typed"
            type="text"
            autoComplete="off"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            className="w-full rounded border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-100"
            disabled={busy}
          />
        </div>
      )}

      {error && <p className="text-sm text-red-400">{error}</p>}

      <button
        type="button"
        onClick={submit}
        disabled={!canSubmit}
        className="w-full rounded bg-emerald-600 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-700"
      >
        {busy ? 'Saving…' : flowMode === 'onboarding' ? 'Confirm & enter office' : 'Save voice mode'}
      </button>
    </div>
  );
}
