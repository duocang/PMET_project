'use client';

// Right-side drawer that previews a file format example. Used by
// FileUpload's header alongside "Use example" so the user can either
// inspect the format or auto-fill a real demo file. Backdrop dims the
// page; Esc / overlay click closes; body scroll is locked while open.

import { useEffect, useState } from 'react';

interface FilePreviewProps {
  title: string;
  content: string;
  /** One-sentence hint about the format, shown under the title. */
  note?: string;
  /** Trigger label. Caller passes the translated string so this stays
   *  i18n-agnostic (the file-preview component itself doesn't pull from
   *  the translation store). */
  triggerLabel: string;
  /** aria-label for the close button. Optional — defaults to "Close". */
  closeLabel?: string;
}

function PreviewIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="11" cy="11" r="8" />
      <path d="m21 21-4.3-4.3" />
    </svg>
  );
}

export default function FilePreview({ title, content, note, triggerLabel, closeLabel = 'Close' }: FilePreviewProps) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('keydown', onKey);
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = '';
    };
  }, [open]);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1 text-xs font-medium text-primary-700 hover:text-primary-800"
      >
        <PreviewIcon />
        {triggerLabel}
      </button>
      {open && (
        <>
          <div
            className="fixed inset-0 z-40 bg-slate-900/30 transition-opacity"
            onClick={() => setOpen(false)}
            aria-hidden
          />
          <aside
            className="fixed inset-y-0 right-0 z-50 flex w-full max-w-lg flex-col border-l border-slate-200 bg-white shadow-2xl"
            role="dialog"
            aria-modal="true"
            aria-label={title}
          >
            <header className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
              <div>
                <p className="text-sm font-semibold text-slate-900">{title}</p>
                {note && <p className="mt-0.5 text-xs text-slate-500">{note}</p>}
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="text-slate-400 hover:text-slate-600"
                aria-label={closeLabel}
              >
                ✕
              </button>
            </header>
            <div className="flex-1 overflow-auto p-5">
              <pre className="whitespace-pre rounded bg-slate-900 px-3 py-2 font-mono text-[12px] leading-relaxed text-slate-100">
                {content}
              </pre>
            </div>
          </aside>
        </>
      )}
    </>
  );
}
