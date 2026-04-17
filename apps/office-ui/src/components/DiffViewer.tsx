'use client';

import type { FC } from 'react';

/**
 * Inline diff renderer for the HITL approval flow.
 *
 * Adapted from the public `claudecodeui` fork
 * (`src/components/DiffViewer.jsx`) — unified-diff lines coloured by
 * prefix: `+` green, `-` red, `@@` blue, everything else slate. Used
 * by `ApprovalPanel` so reviewers looking at a `file_write` can see
 * what the agent is actually proposing to change, instead of a raw
 * command string.
 *
 * The component is intentionally unopinionated about max-height /
 * overflow — the surrounding card decides. We only handle the
 * line-level presentation.
 */
export interface DiffViewerProps {
  diff: string | null | undefined;
  /** When true (mobile), wrap long lines instead of overflowing horizontally. */
  wrapText?: boolean;
  /** Optional aria-label override for screen-reader context. */
  ariaLabel?: string;
}

export const DiffViewer: FC<DiffViewerProps> = ({
  diff,
  wrapText = false,
  ariaLabel = 'Code diff',
}) => {
  if (!diff) {
    return (
      <p className="p-2 text-center font-mono text-[8px] italic text-slate-600">
        No diff available
      </p>
    );
  }

  const lines = diff.split('\n');

  return (
    <div
      role="region"
      aria-label={ariaLabel}
      className="rounded border border-slate-800 bg-black/60"
    >
      {lines.map((line, idx) => {
        // Order matters — file-header markers (`+++`, `---`) must be
        // classified before the single `+` / `-` diff markers.
        const isFileHeaderAdd = line.startsWith('+++');
        const isFileHeaderDel = line.startsWith('---');
        const isHunkHeader = line.startsWith('@@');
        const isAddition = line.startsWith('+') && !isFileHeaderAdd;
        const isDeletion = line.startsWith('-') && !isFileHeaderDel;

        let style = 'text-slate-400';
        if (isAddition) style = 'bg-emerald-950/50 text-emerald-300';
        else if (isDeletion) style = 'bg-red-950/50 text-red-300';
        else if (isHunkHeader) style = 'bg-indigo-950/50 text-indigo-300';
        else if (isFileHeaderAdd || isFileHeaderDel)
          style = 'text-slate-500 italic';

        return (
          <div
            key={idx}
            className={`font-mono text-[8px] px-2 py-px ${
              wrapText
                ? 'whitespace-pre-wrap break-all'
                : 'whitespace-pre overflow-x-auto'
            } ${style}`}
          >
            {line === '' ? '\u00A0' : line}
          </div>
        );
      })}
    </div>
  );
};
