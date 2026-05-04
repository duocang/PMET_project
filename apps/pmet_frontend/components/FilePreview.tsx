'use client';

// Right-side drawer that previews a file format example. Used by
// FileUpload's header alongside "Use example" so the user can either
// inspect the format or auto-fill a real demo file. Backdrop dims the
// page; Esc / overlay click closes; body scroll is locked while open.

import { useEffect, useRef, useState } from 'react';

interface FilePreviewProps {
  title: string;
  /** Static fallback shown immediately while a remote preview loads, or
   *  permanently when no `sourceUrl` is supplied. */
  content: string;
  /** Optional remote source. When set, the drawer fetches it on first
   *  open and replaces the static `content` with as many leading lines
   *  as fit the visible drawer area (no vertical scroll). If the URL
   *  carries a `lines=` query param, we override it with the computed
   *  count so huge files (TAIR10.fasta) don't ship through the wire.
   *  Errors fall back to `content`. */
  sourceUrl?: string;
  /** One-sentence hint about the format, shown under the title. */
  note?: string;
  /** Trigger label. Caller passes the translated string so this stays
   *  i18n-agnostic (the file-preview component itself doesn't pull from
   *  the translation store). */
  triggerLabel: string;
  /** aria-label for the close button. Optional — defaults to "Close". */
  closeLabel?: string;
}

// Layout constants must match the JSX below.
//   - <pre> uses font-size 12px + leading-relaxed (1.625) → 19.5 px/line
//   - <pre> has py-2 = 8px top + 8px bottom = 16 px vertical padding
//   - parent <div> has p-5 = 20px top + 20px bottom = 40 px vertical padding
const LINE_HEIGHT_PX = 19.5;
const VERTICAL_CHROME_PX = 40 /* parent p-5 */ + 16 /* pre py-2 */;
// Last line was getting half-clipped on a few odd viewport heights;
// lopping one more line off keeps the bottom edge clean.
const SAFETY_LINES = 1;
// Don't go below this on tiny viewports — fewer than ~15 lines makes the
// preview useless. The user can always scroll if it overflows on a
// 480-px-tall window; that's an unusual case.
const MIN_LINES = 15;

function PreviewIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="11" cy="11" r="8" />
      <path d="m21 21-4.3-4.3" />
    </svg>
  );
}

export default function FilePreview({ title, content, sourceUrl, note, triggerLabel, closeLabel = 'Close' }: FilePreviewProps) {
  const [open, setOpen] = useState(false);
  const [fetched, setFetched] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

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

  // Measure-then-fetch: wait one rAF after open so the drawer has
  // committed to layout, derive how many lines fit, then build the
  // request URL with that count. Defensive client-side slice covers
  // the catalog-file case where the URL doesn't accept `lines=`.
  useEffect(() => {
    if (!open || !sourceUrl || fetched !== null) return;
    let cancelled = false;

    const run = () => {
      const el = containerRef.current;
      if (!el) {
        // Drawer not yet in the DOM — try again next frame.
        requestAnimationFrame(run);
        return;
      }
      const fitting = Math.max(
        MIN_LINES,
        Math.floor((el.clientHeight - VERTICAL_CHROME_PX) / LINE_HEIGHT_PX) - SAFETY_LINES,
      );

      const url = new URL(sourceUrl, window.location.origin);
      if (url.searchParams.has('lines')) {
        url.searchParams.set('lines', String(fitting));
      }

      setLoading(true);
      fetch(url.toString())
        .then((r) => (r.ok ? r.text() : Promise.reject(new Error(`HTTP ${r.status}`))))
        .then((text) => {
          if (cancelled) return;
          // Always trim client-side: catalog endpoints ignore `lines=`,
          // and even the demo-preview endpoint can return slightly more
          // lines than fitting if rounding goes our way.
          const trimmed = text.split('\n').slice(0, fitting).join('\n');
          setFetched(trimmed);
        })
        .catch((err) => {
          if (cancelled) return;
          console.error('FilePreview fetch failed', err);
          setFetched(content);
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    };

    requestAnimationFrame(run);
    return () => {
      cancelled = true;
    };
  }, [open, sourceUrl, fetched, content]);

  const display = sourceUrl ? (fetched ?? content) : content;

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
            {/* overflow-hidden on the parent so the y-axis really
                doesn't scroll — the only reason a tiny scroll could
                appear is if our line-fit math is one row off, in which
                case clipping is the desired behaviour, not a scrollbar. */}
            <div ref={containerRef} className="flex-1 overflow-hidden p-5">
              <pre className="whitespace-pre overflow-x-auto rounded bg-slate-900 px-3 py-2 font-mono text-[12px] leading-relaxed text-slate-100">
                {display}
                {loading && sourceUrl && fetched === null && '\n\n…'}
              </pre>
            </div>
          </aside>
        </>
      )}
    </>
  );
}
