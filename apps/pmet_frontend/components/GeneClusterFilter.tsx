'use client';

import { useEffect, useState } from 'react';
import { useTranslation } from '@/lib/i18n';

// Same palette as scripts/r/process_pmet_result.R's COLORS constant and
// the /visualize page's CLUSTER_COLORS, modulo'd for >7 clusters. Using
// one palette across submit-time filter, embedded quick-look heatmap,
// and the standalone explorer keeps the visual identity stable for a
// given cluster across the whole flow.
const PALETTE = [
  '#ed3333', // red
  '#1a94bc', // blue
  '#40a070', // green
  '#fc6315', // orange
  '#f9a633', // mustard
  '#8b2671', // purple
  '#2f2f35', // near-black
];

interface ClusterInfo {
  name: string;
  count: number;
}

interface Props {
  file: File | null;
  // Reports the user's selection. Two-state contract:
  //   - null: no filter step needed at submit. Either the gene list
  //     has only a single column (no clusters to filter on), or every
  //     detected cluster is still active. The submit handler should
  //     pass the original file through untouched.
  //   - string[]: at least one cluster is deactivated. The array
  //     lists the names that should *remain* in the submitted file;
  //     the submit handler builds a filtered copy and uploads that.
  onSelectionChange: (active: string[] | null) => void;
}

export default function GeneClusterFilter({ file, onSelectionChange }: Props) {
  const { t } = useTranslation();
  const [clusters, setClusters] = useState<ClusterInfo[] | null>(null);
  const [active, setActive] = useState<Set<string>>(new Set());
  const [open, setOpen] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Re-parse whenever a new File arrives. Clearing the file resets
  // every internal piece of state plus the upstream selection so a
  // freshly-uploaded list starts with all clusters active.
  useEffect(() => {
    if (!file) {
      setClusters(null);
      setActive(new Set());
      setError(null);
      onSelectionChange(null);
      return;
    }
    const reader = new FileReader();
    reader.onerror = () => setError(t('cluster_filter.err.read'));
    reader.onload = () => {
      const text = (reader.result as string) ?? '';
      const counts: Record<string, number> = {};
      // Probe the first non-blank line: a single whitespace-separated
      // token means the file has no cluster column, so the panel has
      // nothing to offer and we report null up front.
      let probed = false;
      let isSingleColumn = false;
      for (const rawLine of text.split('\n')) {
        const line = rawLine.replace(/\r$/, '').trim();
        if (!line) continue;
        const parts = line.split(/\s+/).filter(Boolean);
        if (!probed) {
          probed = true;
          isSingleColumn = parts.length < 2;
          if (isSingleColumn) break;
        }
        const cluster = parts[0];
        counts[cluster] = (counts[cluster] ?? 0) + 1;
      }
      if (isSingleColumn || Object.keys(counts).length === 0) {
        setClusters(null);
        setActive(new Set());
        onSelectionChange(null);
        return;
      }
      // Show the heaviest clusters first — readers usually want to
      // start by deciding whether to drop the dominant ones.
      const sorted = Object.entries(counts)
        .map(([name, count]) => ({ name, count }))
        .sort((a, b) => b.count - a.count);
      setClusters(sorted);
      const all = new Set(sorted.map((c) => c.name));
      setActive(all);
      // All-active === default === no filter needed at submit.
      onSelectionChange(null);
    };
    reader.readAsText(file);
    // Effect runs only on file change; onSelectionChange is stable
    // enough in practice that re-running on its identity would just
    // cause spurious resets.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file]);

  // Whenever the active set changes, re-decide whether the upstream
  // sees null (no filter) or the explicit list.
  const reportSelection = (next: Set<string>) => {
    if (!clusters) return;
    if (next.size === clusters.length) {
      onSelectionChange(null);
    } else {
      onSelectionChange(Array.from(next));
    }
  };

  const toggle = (name: string) => {
    setActive((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      reportSelection(next);
      return next;
    });
  };

  const selectAll = () => {
    if (!clusters) return;
    const all = new Set(clusters.map((c) => c.name));
    setActive(all);
    reportSelection(all);
  };

  const clearAll = () => {
    setActive(new Set());
    reportSelection(new Set());
  };

  if (error) return <div className="mt-2 text-xs text-red-600">{error}</div>;
  if (!clusters || clusters.length === 0) return null;

  return (
    <div className="mt-3 rounded-md border border-slate-200 bg-slate-50">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-3 py-2 text-left text-xs font-medium text-slate-700 hover:bg-slate-100"
      >
        <span>
          {t('cluster_filter.title')} · {active.size}/{clusters.length}{' '}
          {t('cluster_filter.active_suffix')}
        </span>
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={`transition-transform ${open ? 'rotate-180' : ''}`}
          aria-hidden
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>
      {open && (
        <div className="border-t border-slate-200 px-3 py-2.5">
          <p className="mb-2 text-[11px] text-slate-500">
            {t('cluster_filter.help')}
          </p>
          <div className="mb-2 flex flex-wrap gap-1.5">
            {clusters.map((c, i) => {
              const color = PALETTE[i % PALETTE.length];
              const on = active.has(c.name);
              return (
                <button
                  key={c.name}
                  type="button"
                  onClick={() => toggle(c.name)}
                  // Active chip: translucent (~20%) tint of the cluster
                  // color so multiple chips can sit next to each other
                  // without becoming visually overwhelming. Inactive:
                  // slate-100 + line-through, signaling "excluded".
                  className={`rounded-full border px-2.5 py-1 text-xs font-medium transition-opacity ${
                    on
                      ? 'border-transparent text-slate-800 hover:opacity-90'
                      : 'border-slate-200 bg-slate-100 text-slate-400 line-through hover:bg-slate-200'
                  }`}
                  style={on ? { backgroundColor: `${color}33` } : undefined}
                  title={c.name}
                >
                  <span className="font-mono">{c.name}</span>
                  <span className="ml-1 tabular-nums opacity-60">
                    ({c.count.toLocaleString()})
                  </span>
                </button>
              );
            })}
          </div>
          <div className="flex gap-3 text-xs text-slate-500">
            <button
              type="button"
              onClick={selectAll}
              className="hover:text-slate-800 hover:underline"
              disabled={active.size === clusters.length}
            >
              {t('cluster_filter.select_all')}
            </button>
            <span className="text-slate-300">·</span>
            <button
              type="button"
              onClick={clearAll}
              className="hover:text-slate-800 hover:underline"
              disabled={active.size === 0}
            >
              {t('cluster_filter.clear')}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
