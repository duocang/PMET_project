'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { adminApi } from '@/lib/api';
import { useAdminStore } from '@/lib/adminStore';
import { useTranslation } from '@/lib/i18n';

export function DangerZone() {
  const { t } = useTranslation();
  const router = useRouter();
  const reset = useAdminStore((s) => s.reset);
  const [busy, setBusy] = useState(false);
  const [newToken, setNewToken] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const rotate = async () => {
    if (!confirm(t('admin.danger.rotate.confirm'))) return;
    setBusy(true);
    setErr(null);
    try {
      const r = await adminApi.rotateToken();
      setNewToken(r.token);
      // Do NOT reset() here. /admin's auth guard watches isAdmin and
      // would yank us off the page before the user has read the modal
      // (the new token is shown exactly once). We defer the reset
      // until "Go to login" is clicked, by which point the user has
      // had a chance to copy it.
    } catch (e: any) {
      setErr(e?.message ?? 'Failed');
    } finally {
      setBusy(false);
    }
  };

  const dismiss = () => {
    setNewToken(null);
    // Server already deleted our cookie; mirror that locally so the
    // nav tab disappears, then send the user to log in with the new
    // token they just copied.
    reset();
    router.replace('/admin/login');
  };

  return (
    <div className="card border-red-200 bg-red-50/40">
      <h3 className="mb-2 text-sm font-semibold uppercase tracking-wider text-red-700">
        {t('admin.danger.title')}
      </h3>
      <p className="mb-3 text-sm text-slate-600">{t('admin.danger.rotate.help')}</p>
      <button
        onClick={rotate}
        disabled={busy}
        className="rounded-md border border-red-300 bg-white px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-100 disabled:opacity-50"
      >
        {busy ? t('admin.danger.rotate.busy') : t('admin.danger.rotate.button')}
      </button>
      {err && <div className="mt-3 text-sm text-red-700">{err}</div>}

      {newToken && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-sm p-4">
          <div className="card max-w-lg space-y-4">
            <h4 className="text-base font-semibold text-slate-900">
              {t('admin.danger.rotate.modal.title')}
            </h4>
            <p className="text-sm text-slate-600">
              {t('admin.danger.rotate.modal.body')}
            </p>
            <code className="block break-all rounded-md bg-slate-100 px-3 py-2 font-mono text-xs text-slate-800">
              {newToken}
            </code>
            <div className="flex items-center gap-3">
              <button
                onClick={() => navigator.clipboard.writeText(newToken)}
                className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100"
              >
                {t('admin.danger.rotate.modal.copy')}
              </button>
              <button onClick={dismiss} className="btn-primary">
                {t('admin.danger.rotate.modal.done')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
