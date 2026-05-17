'use client';

import { useEffect, useState } from 'react';
import { adminApi, AdminStatsResponse } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';
import { SubmitTrend } from './charts/SubmitTrend';
import { StatusDonut } from './charts/StatusDonut';
import { RuntimeHistogram } from './charts/RuntimeHistogram';
import { TopErrorsTable } from './charts/TopErrorsTable';

type RangeKey = '7' | '30' | '90';

const RANGES: { key: RangeKey; days: number; labelKey: 'admin.stats.range.7d' | 'admin.stats.range.30d' | 'admin.stats.range.90d' }[] = [
  { key: '7', days: 7, labelKey: 'admin.stats.range.7d' },
  { key: '30', days: 30, labelKey: 'admin.stats.range.30d' },
  { key: '90', days: 90, labelKey: 'admin.stats.range.90d' },
];

export function StatsPanel() {
  const { t } = useTranslation();
  const [days, setDays] = useState<number>(30);
  const [data, setData] = useState<AdminStatsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setErr(null);
    adminApi
      .stats(days)
      .then((r) => {
        if (alive) setData(r);
      })
      .catch((e) => {
        if (alive) setErr(e?.message ?? 'Failed');
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [days]);

  const totalTasks = data
    ? Object.values(data.status_distribution).reduce((a, b) => a + b, 0)
    : 0;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <span className="text-xs uppercase tracking-wider text-slate-500">
          {t('admin.stats.range.label')}
        </span>
        <div className="flex gap-1 rounded-md bg-slate-100 p-1">
          {RANGES.map((r) => (
            <button
              key={r.key}
              onClick={() => setDays(r.days)}
              className={`rounded px-2.5 py-1 text-xs font-medium transition-colors ${
                days === r.days
                  ? 'bg-white text-slate-900 shadow-sm'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              {t(r.labelKey)}
            </button>
          ))}
        </div>
      </div>

      {loading && !data && (
        <div className="card text-sm text-slate-500">{t('admin.stats.loading')}</div>
      )}
      {err && (
        <div className="card text-sm text-red-700">{t('admin.stats.error')}: {err}</div>
      )}
      {data && !err && (
        <>
          {totalTasks === 0 ? (
            <div className="card text-sm text-slate-500">{t('admin.stats.empty')}</div>
          ) : (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <div className="card">
                <h3 className="mb-3 text-sm font-semibold text-slate-700">
                  {t('admin.stats.trend.title')}
                </h3>
                <SubmitTrend trend={data.submit_trend} />
              </div>
              <div className="card">
                <h3 className="mb-3 text-sm font-semibold text-slate-700">
                  {t('admin.stats.status.title')}
                </h3>
                <StatusDonut distribution={data.status_distribution} />
              </div>
              <div className="card lg:col-span-2">
                <h3 className="mb-3 text-sm font-semibold text-slate-700">
                  {t('admin.stats.runtime.title')}
                </h3>
                <RuntimeHistogram byMode={data.runtime_by_mode} />
              </div>
              <div className="card lg:col-span-2">
                <h3 className="mb-3 text-sm font-semibold text-slate-700">
                  {t('admin.stats.errors.title')}
                </h3>
                <TopErrorsTable errors={data.top_errors} />
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
