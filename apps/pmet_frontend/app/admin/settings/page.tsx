'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { adminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

export default function AdminSettingsPage() {
  const router = useRouter();
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [notifyOnSubmit, setNotifyOnSubmit] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const me = await adminApi.me();
        if (!me.is_admin) {
          router.replace('/admin/login?next=/admin/settings');
          return;
        }
        const settings = await adminApi.getSettings();
        if (alive) setNotifyOnSubmit(settings.notify_on_submit);
      } catch (e: any) {
        if (alive) setErr(e?.message ?? 'Failed to load settings');
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [router]);

  const save = async () => {
    setSaving(true);
    setErr(null);
    try {
      const result = await adminApi.updateSettings({ notify_on_submit: notifyOnSubmit });
      setNotifyOnSubmit(result.notify_on_submit);
      setSavedAt(Date.now());
    } catch (e: any) {
      setErr(e?.message ?? 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  const logout = async () => {
    await adminApi.logout();
    router.replace('/admin/login');
  };

  if (loading) {
    return <div className="mx-auto max-w-3xl py-12 text-slate-500">{t('admin.settings.loading')}</div>;
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 py-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">{t('admin.settings.title')}</h1>
        <button onClick={logout} className="text-sm text-slate-500 hover:text-slate-700">
          {t('admin.settings.logout')}
        </button>
      </div>

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
    </div>
  );
}
