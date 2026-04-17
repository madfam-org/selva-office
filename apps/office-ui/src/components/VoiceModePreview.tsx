'use client';

import type { VoiceModePreview as PreviewData } from '@/hooks/useVoiceMode';

interface Props {
  preview: PreviewData;
  showHeadsUp?: boolean;
}

export function VoiceModePreview({ preview, showHeadsUp = true }: Props) {
  const isUserDirect = preview.mode === 'user_direct';
  return (
    <div className="space-y-4 rounded-md border border-slate-700 bg-slate-900/60 p-4 text-sm">
      <div>
        <h3 className="text-base font-semibold text-slate-100">{preview.label}</h3>
        <p className="mt-1 text-xs text-slate-400">Clause version: {preview.clause_version}</p>
      </div>
      {showHeadsUp && (
        <div
          className={
            isUserDirect
              ? 'rounded border border-amber-600/60 bg-amber-950/40 p-3 text-amber-200'
              : 'rounded border border-slate-600/50 bg-slate-800/40 p-3 text-slate-300'
          }
        >
          <p className="text-xs font-bold uppercase tracking-wide">Heads up</p>
          <p className="mt-1 leading-relaxed">{preview.heads_up}</p>
        </div>
      )}
      <div className="text-slate-300">
        <p className="text-xs font-bold uppercase tracking-wide text-slate-400">Consent clause</p>
        <p className="mt-1 whitespace-pre-line leading-relaxed">{preview.clause_body}</p>
      </div>
    </div>
  );
}
