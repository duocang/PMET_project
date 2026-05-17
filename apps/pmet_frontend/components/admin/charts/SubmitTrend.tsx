'use client';

import dynamic from 'next/dynamic';
import type { AdminTrendPoint } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

const Plot = dynamic(() => import('react-plotly.js'), { ssr: false });

interface Props {
  trend: AdminTrendPoint[];
}

export function SubmitTrend({ trend }: Props) {
  const { t } = useTranslation();
  const x = trend.map((p) => p.date);
  // Stack completed / failed / cancelled as the three outcomes; the
  // "submitted" total is the sum of the three plus any still pending /
  // running on that day. Drawing it as a transparent line on top makes
  // the busy-day envelope obvious without doubling the y-axis math.
  const traces = [
    {
      type: 'bar' as const,
      name: t('admin.stats.trend.legend.completed'),
      x,
      y: trend.map((p) => p.completed),
      marker: { color: '#16a34a' },
    },
    {
      type: 'bar' as const,
      name: t('admin.stats.trend.legend.failed'),
      x,
      y: trend.map((p) => p.failed),
      marker: { color: '#dc2626' },
    },
    {
      type: 'bar' as const,
      name: t('admin.stats.trend.legend.cancelled'),
      x,
      y: trend.map((p) => p.cancelled),
      marker: { color: '#94a3b8' },
    },
    {
      type: 'scatter' as const,
      mode: 'lines+markers' as const,
      name: t('admin.stats.trend.legend.submitted'),
      x,
      y: trend.map((p) => p.submitted),
      line: { color: '#1d4ed8', width: 2 },
      marker: { size: 4 },
    },
  ];

  return (
    <Plot
      data={traces}
      layout={{
        autosize: true,
        height: 280,
        margin: { l: 40, r: 12, t: 8, b: 40 },
        barmode: 'stack',
        legend: { orientation: 'h', y: -0.22 },
        xaxis: { type: 'date', showgrid: false },
        yaxis: { gridcolor: '#e2e8f0', zerolinecolor: '#cbd5e1' },
      }}
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: '100%' }}
      useResizeHandler
    />
  );
}
