'use client';

import { useEffect, useState } from 'react';
import { fileApi, FilePreview } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';
import { formatBytes } from '@/lib/runtime';

// Side-drawer preview for user-uploaded inputs on the task detail page.
// Only files inside results/app/<task_id>/upload/ are previewable —
// server-side reference data (TAIR10 FASTA, motif libraries, precomputed
// indexes) is intentionally excluded by the backend (returns 403).
//
// Two render modes:
//   - 'lines'  : gene / interval lists. One identifier per line with no
//                whitespace. Rendered as a paginated table with row
//                numbers so users can spot duplicates / count rows.
//   - 'text'   : everything else (FASTA, GFF3, MEME). Rendered as a
//                monospace block with byte-cap awareness.
// Mode is auto-detected from slot + content rather than mime; FASTA
// is technically also line-oriented but its lines are sequence chunks
// not records and a "table" view of it is misleading.
//
// Truncation: the backend caps preview at ~1 MiB; the drawer surfaces
// "showing first N of M" up front so users know they're not seeing the
// full file.

type Slot = 'genes' | 'fasta' | 'gff3' | 'meme';

interface Props {
  taskId: string;
  slot: Slot;
  onClose: () => void;
}

const PAGE_SIZE = 100;

export default function FileDrawer({ taskId, slot, onClose }: Props) {
  const { t } = useTranslation();
  const [preview, setPreview] = useState<FilePreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setPreview(null);
    setPage(0);
    (async () => {
      try {
        const data = await fileApi.previewUpload(taskId, slot);
        if (!cancelled) setPreview(data);
      } catch {
        if (!cancelled) setError(t('drawer.err.failed'));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [taskId, slot, t]);

  // Esc closes — common drawer affordance.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const isLines = preview && slot === 'genes';
  // Strip trailing CR (Windows / mixed line endings) and skip blank lines.
  const rawLines = isLines && preview
    ? preview.content.split('\n').map((l) => l.replace(/\r$/, '')).filter((l) => l.length > 0)
    : [];
  // Pre-computed promoters and clustered submissions ship a two-column
  // gene list: <cluster>\t<gene>. Plain (un-clustered) submissions ship
  // a single column: just <gene>. Probe the first line to pick the
  // rendering — multi-column mode shows column headers, single-column
  // falls back to a generic identifier label.
  const probe = rawLines[0] ? rawLines[0].split(/\s+/).filter(Boolean) : [];
  const twoColumn = probe.length >= 2;
  const lineRows: string[][] = rawLines.map((l) => {
    if (!twoColumn) return [l];
    const parts = l.split(/\s+/).filter(Boolean);
    // Cluster is the first whitespace token; the remainder is the gene
    // identifier (gene names never contain whitespace in practice, so
    // joining with a space is just defensive).
    return [parts[0] ?? '', parts.slice(1).join(' ')];
  });
  const pageStart = page * PAGE_SIZE;
  const pageRows = lineRows.slice(pageStart, pageStart + PAGE_SIZE);
  const totalPages = Math.max(1, Math.ceil(lineRows.length / PAGE_SIZE));

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-slate-900/40 transition-opacity"
        onClick={onClose}
        aria-hidden
      />
      {/* Drawer */}
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby="file-drawer-title"
        className="fixed inset-y-0 right-0 z-50 flex w-full max-w-2xl flex-col bg-white shadow-xl"
      >
        {/* Header */}
        <header className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <div className="min-w-0">
            <h2
              id="file-drawer-title"
              className="truncate font-mono text-sm font-semibold text-slate-900"
              title={preview?.filename}
            >
              {preview?.filename ?? t('drawer.loading')}
            </h2>
            {preview && (
              <p className="mt-0.5 text-xs text-slate-500">
                {formatBytes(preview.size_bytes)}
                {preview.line_count != null && (
                  <>
                    {' · '}
                    {preview.line_count.toLocaleString()} {t('drawer.lines_suffix')}
                  </>
                )}
                {preview.truncated && (
                  <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-800">
                    {t('drawer.truncated')}
                  </span>
                )}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="ml-4 rounded p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-800"
            aria-label={t('drawer.close')}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M6 6l12 12M6 18L18 6" />
            </svg>
          </button>
        </header>

        {/* Body */}
        <div className="flex-1 overflow-auto">
          {loading && (
            <div className="p-6 text-sm text-slate-500">{t('drawer.loading')}</div>
          )}
          {error && (
            <div className="p-6 text-sm text-red-600">{error}</div>
          )}
          {!loading && !error && preview && isLines && (
            <div>
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="w-16 px-4 py-2 text-right font-medium">#</th>
                    {twoColumn ? (
                      <>
                        <th className="px-4 py-2 text-left font-medium">
                          {t('drawer.col.cluster')}
                        </th>
                        <th className="px-4 py-2 text-left font-medium">
                          {t('drawer.col.gene')}
                        </th>
                      </>
                    ) : (
                      <th className="px-4 py-2 text-left font-medium">
                        {t('drawer.col.gene')}
                      </th>
                    )}
                  </tr>
                </thead>
                <tbody className="font-mono text-slate-700">
                  {pageRows.map((cells, i) => (
                    <tr key={pageStart + i} className="border-t border-slate-100 hover:bg-slate-50">
                      <td className="px-4 py-1 text-right tabular-nums text-slate-400">
                        {pageStart + i + 1}
                      </td>
                      {cells.map((c, j) => (
                        <td key={j} className="px-4 py-1 break-all">{c}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              {lineRows.length === 0 && (
                <div className="p-6 text-sm text-slate-500">{t('drawer.empty')}</div>
              )}
            </div>
          )}
          {!loading && !error && preview && !isLines && (
            <pre className="m-0 whitespace-pre p-4 font-mono text-xs leading-relaxed text-slate-700">
              {preview.content}
            </pre>
          )}
        </div>

        {/* Footer: pagination for lines mode, truncation note otherwise */}
        {!loading && !error && preview && (
          <footer className="border-t border-slate-200 px-5 py-3 text-xs text-slate-500">
            {isLines && lineRows.length > PAGE_SIZE ? (
              <div className="flex items-center justify-between">
                <span>
                  {t('drawer.page.range')
                    .replace('{from}', String(pageStart + 1))
                    .replace('{to}', String(Math.min(pageStart + PAGE_SIZE, lineRows.length)))
                    .replace('{total}', lineRows.length.toLocaleString())}
                </span>
                <div className="flex gap-1">
                  <button
                    type="button"
                    disabled={page === 0}
                    onClick={() => setPage((p) => Math.max(0, p - 1))}
                    className="rounded border border-slate-200 px-2 py-1 text-xs disabled:opacity-40 hover:bg-slate-50"
                  >
                    {t('drawer.page.prev')}
                  </button>
                  <span className="px-2 py-1 tabular-nums">
                    {page + 1} / {totalPages}
                  </span>
                  <button
                    type="button"
                    disabled={page >= totalPages - 1}
                    onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                    className="rounded border border-slate-200 px-2 py-1 text-xs disabled:opacity-40 hover:bg-slate-50"
                  >
                    {t('drawer.page.next')}
                  </button>
                </div>
              </div>
            ) : preview.truncated ? (
              <span>
                {t('drawer.truncated.note').replace(
                  '{size}',
                  formatBytes(preview.size_bytes)
                )}
              </span>
            ) : (
              <span>
                {isLines && lineRows.length > 0
                  ? `${lineRows.length.toLocaleString()} ${t('drawer.lines_suffix')}`
                  : t('drawer.full')}
              </span>
            )}
          </footer>
        )}
      </aside>
    </>
  );
}
