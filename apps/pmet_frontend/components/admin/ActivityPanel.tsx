'use client';

import { useEffect, useState } from 'react';
import { adminApi, AdminAuditRecord } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

type Tab = 'admin' | 'mail';

export function ActivityPanel() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>('admin');
  const [records, setRecords] = useState<AdminAuditRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setErr(null);
    adminApi
      .audit({ n: 50, category: tab })
      .then((r) => {
        if (alive) setRecords(r.records);
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
  }, [tab]);

  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-700">
          {t('admin.audit.title')}
        </h3>
        <div className="flex gap-1 rounded-md bg-slate-100 p-1">
          {(['admin', 'mail'] as Tab[]).map((tk) => (
            <button
              key={tk}
              onClick={() => setTab(tk)}
              className={`rounded px-2.5 py-1 text-xs font-medium transition-colors ${
                tab === tk ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              {t(tk === 'admin' ? 'admin.audit.tab.admin' : 'admin.audit.tab.mail')}
            </button>
          ))}
        </div>
      </div>

      {loading && <div className="text-sm text-slate-500">{t('admin.audit.loading')}</div>}
      {err && <div className="text-sm text-red-700">{err}</div>}
      {!loading && !err && records.length === 0 && (
        <div className="text-sm text-slate-500">{t('admin.audit.empty')}</div>
      )}

      {records.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-200 text-left font-semibold uppercase tracking-wider text-slate-500">
                <th className="py-1 pr-3">{t('admin.audit.col.time')}</th>
                <th className="py-1 pr-3">{t('admin.audit.col.action')}</th>
                <th className="py-1 pr-3">{t('admin.audit.col.target')}</th>
                <th className="py-1 pr-3">{t('admin.audit.col.ip')}</th>
                <th className="py-1 pl-3 text-right">{t('admin.audit.col.ok')}</th>
              </tr>
            </thead>
            <tbody>
              {records.map((r, i) => (
                <tr key={i} className="border-b border-slate-100">
                  <td className="py-1 pr-3 font-mono text-slate-600">{r.ts}</td>
                  <td className="py-1 pr-3 font-medium text-slate-800">{r.action}</td>
                  <td className="py-1 pr-3 font-mono text-slate-700">{r.target || '—'}</td>
                  <td className="py-1 pr-3 font-mono text-slate-500">{r.ip || '—'}</td>
                  <td className={`py-1 pl-3 text-right font-medium ${r.ok ? 'text-emerald-700' : 'text-red-700'}`}>
                    {r.ok ? '✓' : '✗'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
