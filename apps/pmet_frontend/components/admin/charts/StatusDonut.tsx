'use client';

import dynamic from 'next/dynamic';
import { useTranslation } from '@/lib/i18n';

const Plot = dynamic(() => import('react-plotly.js'), { ssr: false });

interface Props {
  distribution: Record<string, number>;
}

// Stable order so re-renders don't flip the slices. Statuses not in this
// list are appended at the end in their original key order.
const ORDER = ['completed', 'failed', 'cancelled', 'running', 'pending'];

const COLORS: Record<string, string> = {
  completed: '#16a34a',
  failed: '#dc2626',
  cancelled: '#94a3b8',
  running: '#0ea5e9',
  pending: '#eab308',
};

export function StatusDonut({ distribution }: Props) {
  const { t } = useTranslation();
  const keys: string[] = [];
  for (const k of ORDER) if (k in distribution) keys.push(k);
  for (const k of Object.keys(distribution)) if (!keys.includes(k)) keys.push(k);

  const values = keys.map((k) => distribution[k]);
  const labels = keys.map((k) => {
    // Reuse the existing tasks.status.* keys when available.
    const key = `tasks.status.${k}` as const;
    try { return t(key as any); } catch { return k; }
  });
  const colors = keys.map((k) => COLORS[k] || '#cbd5e1');
  const total = values.reduce((a, b) => a + b, 0);

  return (
    <Plot
      data={[
        {
          type: 'pie',
          hole: 0.55,
          labels,
          values,
          marker: { colors },
          textinfo: 'percent',
          hoverinfo: 'label+value+percent',
          sort: false,
        },
      ]}
      layout={{
        autosize: true,
        height: 280,
        margin: { l: 8, r: 8, t: 8, b: 8 },
        showlegend: true,
        legend: { orientation: 'v', x: 1, y: 0.5 },
        annotations: [
          {
            text: String(total),
            x: 0.5,
            y: 0.5,
            showarrow: false,
            font: { size: 22, color: '#0f172a' },
          },
        ],
      }}
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: '100%' }}
      useResizeHandler
    />
  );
}
