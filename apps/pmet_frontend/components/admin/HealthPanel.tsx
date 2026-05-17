'use client';

import { useState } from 'react';
import { adminApi, HealthCheck } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

const STATUS_COLOR: Record<HealthCheck['status'], string> = {
  ok: 'bg-emerald-100 text-emerald-800',
  warn: 'bg-amber-100 text-amber-800',
  fail: 'bg-red-100 text-red-800',
};

const STATUS_DOT: Record<HealthCheck['status'], string> = {
  ok: 'bg-emerald-500',
  warn: 'bg-amber-500',
  fail: 'bg-red-500',
};

export function HealthPanel() {
  const { t } = useTranslation();
  const [checks, setChecks] = useState<HealthCheck[] | null>(null);
  const [running, setRunning] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const run = async () => {
    setRunning(true);
    setErr(null);
    try {
      const r = await adminApi.health();
      setChecks(r.checks);
    } catch (e: any) {
      setErr(e?.message ?? 'Failed');
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-700">{t('admin.health.title')}</h3>
        <button
          onClick={run}
          disabled={running}
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-50"
        >
          {running ? t('admin.health.running') : t('admin.health.run')}
        </button>
      </div>

      {err && <div className="text-sm text-red-700">{err}</div>}
      {!checks && !running && !err && (
        <div className="text-sm text-slate-500">{t('admin.health.idle')}</div>
      )}

      {checks && (
        <ul className="space-y-2 text-sm">
          {checks.map((c) => (
            <li key={c.name} className="rounded-md border border-slate-200 p-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className={`inline-block h-2 w-2 rounded-full ${STATUS_DOT[c.status]}`} />
                  <span className="font-medium text-slate-800">
                    {t(`admin.health.check.${c.name}` as any) || c.name}
                  </span>
                </div>
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-semibold uppercase ${STATUS_COLOR[c.status]}`}
                >
                  {c.status}
                </span>
              </div>
              <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-all font-mono text-xs text-slate-500">
                {JSON.stringify(c.detail, null, 0)}
              </pre>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
