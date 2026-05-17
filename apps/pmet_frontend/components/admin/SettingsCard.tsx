'use client';

import { useEffect, useState } from 'react';
import { adminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

export function SettingsCard() {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [notifyOnSubmit, setNotifyOnSubmit] = useState(true);
  const [notifyUserOnStart, setNotifyUserOnStart] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const settings = await adminApi.getSettings();
        if (alive) {
          setNotifyOnSubmit(settings.notify_on_submit);
          setNotifyUserOnStart(settings.notify_user_on_start);
        }
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
      const result = await adminApi.updateSettings({
        notify_on_submit: notifyOnSubmit,
        notify_user_on_start: notifyUserOnStart,
      });
      setNotifyOnSubmit(result.notify_on_submit);
      setNotifyUserOnStart(result.notify_user_on_start);
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
    <div className="card">
      <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-slate-500">
        {t('admin.settings.section.notifications')}
      </h2>
      <label className="flex cursor-pointer items-start gap-3">
        <input
          type="checkbox"
          checked={notifyOnSubmit}
          onChange={(e) => setNotifyOnSubmit(e.target.checked)}
          className="mt-1 h-4 w-4 cursor-pointer"
        />
        <span>
          <div className="font-medium text-slate-900">
            {t('admin.settings.notify_on_submit.label')}
          </div>
          <div className="text-sm text-slate-500">
            {t('admin.settings.notify_on_submit.help')}
          </div>
        </span>
      </label>

      <label className="mt-5 flex cursor-pointer items-start gap-3 border-t border-slate-100 pt-5">
        <input
          type="checkbox"
          checked={notifyUserOnStart}
          onChange={(e) => setNotifyUserOnStart(e.target.checked)}
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

      {err && (
        <div className="mt-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{err}</div>
      )}

      <div className="mt-6 flex items-center gap-4">
        <button onClick={save} disabled={saving} className="btn-primary disabled:opacity-50">
          {saving ? t('admin.settings.saving') : t('admin.settings.save')}
        </button>
        {savedAt && (
          <span className="text-sm text-emerald-700">{t('admin.settings.saved')}</span>
        )}
      </div>
    </div>
  );
}
