'use client';

import { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import { resultsApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

// Replaces the standalone /tasks/[id]/visualize route — that was a second,
// stripped-down visualizer that diverged from the rich /visualize page.
// This embedded summary covers the at-a-glance need (did my run look
// reasonable? where do the significant pairs sit?) while the "Open in
// Viewer" CTA on the task detail page links to /visualize?task=<id> for
// full exploration.
const Plot = dynamic(() => import('react-plotly.js'), { ssr: false });

interface MotifRow {
  cluster: string;
  motif1: string;
  motif2: string;
  gene_num: number;
  total_genes: number;
  cluster_genes: number;
  p_adj_bh: number;
}

interface ClusterInfo {
  name: string;
  count: number;
}

interface Histogram {
  bin_edges: number[];
  counts: number[];
}

interface Summary {
  total_pairs: number;
  num_clusters: number;
  num_unique_motifs: number;
  significant_pairs_005: number;
  clusters?: ClusterInfo[];
  histogram?: Histogram;
}

interface Props {
  taskId: string;
}

const TOP_N = 10;

export default function TaskQuickLook({ taskId }: Props) {
  const { t } = useTranslation();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [topRows, setTopRows] = useState<MotifRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        // Two parallel calls: summary for the headline numbers + histogram,
        // /results sorted ascending by p_adj_bh for the top-N table. The
        // backend already returns rows in file order; the demo's first ten
        // are typically the smallest p-values for that fixture.
        const [s, r] = await Promise.all([
          resultsApi.summary(taskId),
          resultsApi.get(taskId, { limit: TOP_N, offset: 0, p_adj_max: 0.05 }),
        ]);
        if (cancelled) return;
        setSummary(s);
        setTopRows((r?.results as MotifRow[]) ?? []);
      } catch {
        if (!cancelled) setError(t('quicklook.err.failed'));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [taskId, t]);

  if (loading) {
    return (
      <div className="card">
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-slate-500">
          {t('quicklook.title')}
        </h2>
        <div className="text-sm text-slate-500 py-4">{t('quicklook.loading')}</div>
      </div>
    );
  }

  if (error || !summary) {
    return (
      <div className="card">
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-slate-500">
          {t('quicklook.title')}
        </h2>
        <div className="text-sm text-slate-500 py-4">{error ?? t('quicklook.err.failed')}</div>
      </div>
    );
  }

  const histX = summary.histogram?.bin_edges
    ? summary.histogram.bin_edges
        .slice(0, -1)
        .map((e, i) => (e + summary.histogram!.bin_edges[i + 1]) / 2)
    : [];
  const histY = summary.histogram?.counts ?? [];

  return (
    <div className="card">
      <div className="mb-4 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-500">
          {t('quicklook.title')}
        </h2>
        <span className="text-xs text-slate-400">{t('quicklook.subtitle')}</span>
      </div>

      {/* Headline numbers */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 mb-5">
        <Stat label={t('quicklook.stat.total')} value={summary.total_pairs} />
        <Stat label={t('quicklook.stat.clusters')} value={summary.num_clusters} />
        <Stat label={t('quicklook.stat.motifs')} value={summary.num_unique_motifs} />
        <Stat
          label={t('quicklook.stat.sig')}
          value={summary.significant_pairs_005}
          highlight
        />
      </div>

      {/* P-adj histogram (compact) */}
      {histY.length > 0 && (
        <div className="mb-5">
          <h3 className="text-xs font-semibold text-slate-600 mb-1">
            {t('quicklook.histogram.title')}
          </h3>
          <Plot
            data={[
              {
                x: histX,
                y: histY,
                type: 'bar',
                marker: { color: '#1a94bc' },
                hovertemplate: 'p ≈ %{x:.3f}<br>%{y} pairs<extra></extra>',
              },
            ]}
            layout={{
              height: 160,
              margin: { l: 40, r: 10, t: 8, b: 30 },
              xaxis: { title: { text: 'Adj. P-value (BH)', font: { size: 10 } }, tickfont: { size: 9 } },
              yaxis: { tickfont: { size: 9 } },
              bargap: 0.05,
              showlegend: false,
            }}
            config={{ displayModeBar: false, responsive: true }}
            style={{ width: '100%' }}
            useResizeHandler
          />
        </div>
      )}

      {/* Top-N significant pairs */}
      {topRows.length > 0 ? (
        <div>
          <h3 className="text-xs font-semibold text-slate-600 mb-2">
            {t('quicklook.top.title').replace('{n}', String(topRows.length))}
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-slate-500 border-b border-slate-200">
                  <th className="py-1.5 pr-3 font-medium">{t('tviz.col.cluster')}</th>
                  <th className="py-1.5 pr-3 font-medium">{t('tviz.col.motif1')}</th>
                  <th className="py-1.5 pr-3 font-medium">{t('tviz.col.motif2')}</th>
                  <th className="py-1.5 pr-3 font-medium text-right">{t('tviz.col.genes')}</th>
                  <th className="py-1.5 font-medium text-right">{t('tviz.col.padj_bh')}</th>
                </tr>
              </thead>
              <tbody>
                {topRows.map((r, i) => (
                  <tr key={i} className="border-b border-slate-100 last:border-0">
                    <td className="py-1.5 pr-3 text-slate-700">{r.cluster}</td>
                    <td className="py-1.5 pr-3 font-mono text-slate-700">{r.motif1}</td>
                    <td className="py-1.5 pr-3 font-mono text-slate-700">{r.motif2}</td>
                    <td className="py-1.5 pr-3 text-right tabular-nums text-slate-700">
                      {r.gene_num}/{r.cluster_genes}
                    </td>
                    <td className="py-1.5 text-right tabular-nums text-slate-700">
                      {r.p_adj_bh.toExponential(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="text-xs text-slate-500 py-2">{t('quicklook.top.empty')}</div>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  highlight,
}: {
  label: string;
  value: number;
  highlight?: boolean;
}) {
  return (
    <div className="rounded-md bg-slate-50 px-3 py-2 text-center">
      <div
        className={`text-xl font-bold tabular-nums ${
          highlight ? 'text-red-600' : 'text-slate-900'
        }`}
      >
        {value.toLocaleString()}
      </div>
      <div className="text-[10px] uppercase tracking-wide text-slate-500 mt-0.5">{label}</div>
    </div>
  );
}
