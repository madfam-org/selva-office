'use client';

import { useEffect, useRef } from 'react';

import { VoiceModeStep } from '@/components/VoiceModeStep';
import { useFocusTrap } from '@/hooks/useFocusTrap';

interface Props {
  open: boolean;
  onClose: () => void;
  onChanged?: () => void;
}

export function VoiceModeChangeModal({ open, onClose, onChanged }: Props) {
  const trapRef = useFocusTrap<HTMLDivElement>(open);
  const closeBtnRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (open) closeBtnRef.current?.focus();
  }, [open]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-modal flex items-center justify-center bg-black/70 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="voice-mode-modal-title"
    >
      <div
        ref={trapRef}
        className="max-h-[90vh] w-full max-w-xl overflow-y-auto rounded-lg border border-slate-700 bg-slate-900 p-6 shadow-lg"
      >
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            <h2 id="voice-mode-modal-title" className="text-lg font-semibold text-slate-100">
              Change outbound voice mode
            </h2>
            <p className="mt-1 text-xs text-slate-400">
              Your previous selection remains in the consent ledger.
            </p>
          </div>
          <button
            ref={closeBtnRef}
            type="button"
            onClick={onClose}
            className="rounded p-1 text-slate-400 hover:text-slate-100"
            aria-label="Close"
          >
            ✕
          </button>
        </div>
        <VoiceModeStep
          mode="change"
          onDone={() => {
            onChanged?.();
            onClose();
          }}
        />
      </div>
    </div>
  );
}
