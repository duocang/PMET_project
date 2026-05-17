'use client';

import { useEffect, useState } from 'react';
import { adminApi, CleanupReport } from '@/lib/api';
import { useAdminStore } from '@/lib/adminStore';
import { useTranslation } from '@/lib/i18n';

export function CleanupCard() {
  const { t } = useTranslation();
  // Subscribe to the settings-version counter so SettingsCard's PUT
  // triggers a fresh preview here. Otherwise the eligible-count would
  // stay frozen at whatever loaded on mount.
  const settingsVersion = useAdminStore((s) => s.settingsVersion);
  const [eligible, setEligible] = useState<number | null>(null);
  const [retentionDays, setRetentionDays] = useState<number>(0);
  const [running, setRunning] = useState(false);
  const [lastReport, setLastReport] = useState<CleanupReport | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const loadPreview = async () => {
    setErr(null);
    try {
      const r = await adminApi.cleanupPreview();
      setEligible(r.eligible);
      setRetentionDays(r.retention_days);
    } catch (e: any) {
      setErr(e?.message ?? 'Failed');
    }
  };

  useEffect(() => {
    loadPreview();
  }, [settingsVersion]);

  const run = async () => {
    if (eligible == null || eligible === 0) return;
    const msg = t('admin.cleanup.confirm').replace('{n}', String(eligible));
    if (!confirm(msg)) return;
    setRunning(true);
    setErr(null);
    try {
      const r = await adminApi.cleanupRun();
      setLastReport(r);
      await loadPreview();
    } catch (e: any) {
      setErr(e?.message ?? 'Failed');
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="card space-y-3">
      <h3 className="text-sm font-semibold text-slate-700">{t('admin.cleanup.title')}</h3>

      {retentionDays <= 0 ? (
        <div className="text-sm text-slate-500">{t('admin.cleanup.not_configured')}</div>
      ) : (
        <>
          <div className="text-sm text-slate-600">
            {t('admin.cleanup.summary')
              .replace('{days}', String(retentionDays))
              .replace('{n}', String(eligible ?? '…'))}
          </div>
          <button
            onClick={run}
            disabled={running || eligible === 0 || eligible == null}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-50"
          >
            {running ? t('admin.cleanup.running') : t('admin.cleanup.run')}
          </button>
        </>
      )}

      {err && <div className="text-sm text-red-700">{err}</div>}

      {lastReport && (
        <div className="rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-700">
          <div className="font-medium">{t('admin.cleanup.last_report')}</div>
          <ul className="mt-1 space-y-0.5">
            <li>
              {t('admin.cleanup.report.dirs')}: {lastReport.removed_dirs}
            </li>
            <li>
              {t('admin.cleanup.report.zips')}: {lastReport.removed_zips}
            </li>
            <li>
              {t('admin.cleanup.report.metas')}: {lastReport.removed_metas}
            </li>
            {lastReport.errors.length > 0 && (
              <li className="text-red-700">
                {t('admin.cleanup.report.errors')}: {lastReport.errors.length}
              </li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
