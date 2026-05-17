'use client';

import dynamic from 'next/dynamic';
import type { AdminRuntimeStats } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';
import type { TranslationKey } from '@/lib/translations';

const Plot = dynamic(() => import('react-plotly.js'), { ssr: false });

interface Props {
  byMode: Record<string, AdminRuntimeStats>;
}

const MODE_COLOR: Record<string, string> = {
  promoters: '#1d4ed8',
  promoters_pre: '#0ea5e9',
  intervals: '#7c3aed',
};

const fmt = (s: number | null): string => {
  if (s == null) return '–';
  if (s < 60) return `${s.toFixed(0)}s`;
  if (s < 3600) return `${(s / 60).toFixed(1)}m`;
  return `${(s / 3600).toFixed(1)}h`;
};

export function RuntimeHistogram({ byMode }: Props) {
  const { t } = useTranslation();
  const modes = Object.keys(byMode);
  if (modes.length === 0) {
    return <div className="text-sm text-slate-500">{t('admin.stats.empty')}</div>;
  }

  const data = modes.map((mode) => ({
    type: 'histogram' as const,
    name: t(`mode.${mode}` as TranslationKey),
    x: byMode[mode].samples,
    marker: { color: MODE_COLOR[mode] || '#0f172a' },
    opacity: 0.75,
    autobinx: true,
  }));

  return (
    <div className="space-y-3">
      <Plot
        data={data}
        layout={{
          autosize: true,
          height: 280,
          margin: { l: 40, r: 12, t: 8, b: 40 },
          barmode: 'overlay',
          legend: { orientation: 'h', y: -0.22 },
          xaxis: {
            title: { text: t('admin.stats.runtime.axis.seconds') },
            gridcolor: '#e2e8f0',
            zerolinecolor: '#cbd5e1',
          },
          yaxis: {
            title: { text: t('admin.stats.runtime.axis.count') },
            gridcolor: '#e2e8f0',
            zerolinecolor: '#cbd5e1',
          },
        }}
        config={{ displayModeBar: false, responsive: true }}
        style={{ width: '100%' }}
        useResizeHandler
      />
      <ul className="grid grid-cols-1 gap-1 text-xs text-slate-500 sm:grid-cols-3">
        {modes.map((mode) => {
          const s = byMode[mode];
          const summary = t('admin.stats.runtime.summary')
            .replace('{count}', String(s.count))
            .replace('{p50}', fmt(s.p50))
            .replace('{p95}', fmt(s.p95));
          return (
            <li key={mode}>
              <span
                className="inline-block h-2.5 w-2.5 rounded-sm align-middle"
                style={{ background: MODE_COLOR[mode] || '#0f172a' }}
              />{' '}
              <span className="font-medium text-slate-700">{t(`mode.${mode}` as TranslationKey)}</span>
              {' — '}
              {summary}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
