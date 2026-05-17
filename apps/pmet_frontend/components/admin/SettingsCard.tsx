'use client';

import { useEffect, useState } from 'react';
import { adminApi, AdminSettings } from '@/lib/api';
import { useAdminStore } from '@/lib/adminStore';
import { useTranslation } from '@/lib/i18n';

const initial: AdminSettings = {
  notify_on_submit: true,
  notify_user_on_start: true,
  submissions_paused: false,
  admin_notify_email: '',
  minhash_threshold: null,
  result_retention_days: null,
};

// Free-form integer input → API contract. Empty / non-positive collapse
// to null which the backend interprets as "use default".
function parseIntOrNull(raw: string): number | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const n = Number.parseInt(trimmed, 10);
  if (!Number.isFinite(n) || n <= 0) return null;
  return n;
}

export function SettingsCard() {
  const { t } = useTranslation();
  const setSubmissionsPaused = useAdminStore((s) => s.setSubmissionsPaused);
  const bumpSettings = useAdminStore((s) => s.bumpSettings);
  const [loading, setLoading] = useState(true);
  const [s, setS] = useState<AdminSettings>(initial);
  // Number fields render as text so the user can briefly clear them
  // without the input snapping to "0". We hold the raw string and parse
  // on save.
  const [minhashRaw, setMinhashRaw] = useState('');
  const [retentionRaw, setRetentionRaw] = useState('');
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const got = await adminApi.getSettings();
        if (!alive) return;
        setS(got);
        setMinhashRaw(got.minhash_threshold == null ? '' : String(got.minhash_threshold));
        setRetentionRaw(got.result_retention_days == null ? '' : String(got.result_retention_days));
      } catch (e: any) {
        if (alive) setErr(e?.message ?? 'Failed to load settings');
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  const save = async () => {
    setSaving(true);
    setErr(null);
    try {
      const payload: AdminSettings = {
        ...s,
        minhash_threshold: parseIntOrNull(minhashRaw),
        result_retention_days: parseIntOrNull(retentionRaw),
      };
      const result = await adminApi.updateSettings(payload);
      setS(result);
      setMinhashRaw(result.minhash_threshold == null ? '' : String(result.minhash_threshold));
      setRetentionRaw(result.result_retention_days == null ? '' : String(result.result_retention_days));
      // Keep the global store in sync so the /submit banner reacts
      // without waiting for the next AdminInitializer fetch.
      setSubmissionsPaused(result.submissions_paused);
      // Nudge sibling panels (CleanupCard's eligible-count preview) so
      // they re-fetch against the new policy without a page reload.
      bumpSettings();
      setSavedAt(Date.now());
    } catch (e: any) {
      setErr(e?.message ?? 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="card text-slate-500">{t('admin.settings.loading')}</div>;
  }

  return (
    <div className="card space-y-6">
      {/* Maintenance — kill switch for new submissions */}
      <div>
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-500">
          {t('admin.settings.section.maintenance')}
        </h3>
        <label className="flex cursor-pointer items-start gap-3">
          <input
            type="checkbox"
            checked={s.submissions_paused}
            onChange={(e) => setS({ ...s, submissions_paused: e.target.checked })}
            className="mt-1 h-4 w-4 cursor-pointer"
          />
          <span>
            <div className="font-medium text-slate-900">
              {t('admin.settings.submissions_paused.label')}
            </div>
            <div className="text-sm text-slate-500">
              {t('admin.settings.submissions_paused.help')}
            </div>
          </span>
        </label>
      </div>

      {/* Notifications */}
      <div className="border-t border-slate-100 pt-5">
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-500">
          {t('admin.settings.section.notifications')}
        </h3>
        <label className="flex cursor-pointer items-start gap-3">
          <input
            type="checkbox"
            checked={s.notify_on_submit}
            onChange={(e) => setS({ ...s, notify_on_submit: e.target.checked })}
            className="mt-1 h-4 w-4 cursor-pointer"
          />
          <span>
            <div className="font-medium text-slate-900">
              {t('admin.settings.notify_on_submit.label')}
            </div>
            <div className="text-sm text-slate-500">{t('admin.settings.notify_on_submit.help')}</div>
          </span>
        </label>

        <label className="mt-5 flex cursor-pointer items-start gap-3">
          <input
            type="checkbox"
            checked={s.notify_user_on_start}
            onChange={(e) => setS({ ...s, notify_user_on_start: e.target.checked })}
            className="mt-1 h-4 w-4 cursor-pointer"
          />
          <span>
            <div className="font-medium text-slate-900">
              {t('admin.settings.notify_user_on_start.label')}
            </div>
            <div className="text-sm text-slate-500">
              {t('admin.settings.notify_user_on_start.help')}
            </div>
          </span>
        </label>

        <div className="mt-5">
          <label className="mb-1 block text-sm font-medium text-slate-700">
            {t('admin.settings.admin_notify_email.label')}
          </label>
          <input
            type="email"
            value={s.admin_notify_email}
            onChange={(e) => setS({ ...s, admin_notify_email: e.target.value })}
            placeholder={t('admin.settings.admin_notify_email.placeholder')}
            className="input-field"
          />
          <p className="mt-1 text-xs text-slate-500">
            {t('admin.settings.admin_notify_email.help')}
          </p>
        </div>
      </div>

      {/* Advanced — runtime knobs */}
      <div className="border-t border-slate-100 pt-5">
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-500">
          {t('admin.settings.section.advanced')}
        </h3>

        <div>
          <label className="mb-1 block text-sm font-medium text-slate-700">
            {t('admin.settings.minhash_threshold.label')}
          </label>
          <input
            type="number"
            min={1}
            value={minhashRaw}
            onChange={(e) => setMinhashRaw(e.target.value)}
            placeholder={t('admin.settings.minhash_threshold.placeholder')}
            className="input-field"
          />
          <p className="mt-1 text-xs text-slate-500">
            {t('admin.settings.minhash_threshold.help')}
          </p>
        </div>

        <div className="mt-5">
          <label className="mb-1 block text-sm font-medium text-slate-700">
            {t('admin.settings.result_retention_days.label')}
          </label>
          <input
            type="number"
            min={1}
            value={retentionRaw}
            onChange={(e) => setRetentionRaw(e.target.value)}
            placeholder={t('admin.settings.result_retention_days.placeholder')}
            className="input-field"
          />
          <p className="mt-1 text-xs text-slate-500">
            {t('admin.settings.result_retention_days.help')}
          </p>
        </div>
      </div>

      {err && (
        <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{err}</div>
      )}

      <div className="flex items-center gap-4">
        <button onClick={save} disabled={saving} className="btn-primary disabled:opacity-50">
          {saving ? t('admin.settings.saving') : t('admin.settings.save')}
        </button>
        {savedAt && <span className="text-sm text-emerald-700">{t('admin.settings.saved')}</span>}
      </div>
    </div>
  );
}
