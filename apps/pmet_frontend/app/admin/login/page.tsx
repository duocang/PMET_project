'use client';

import { useState } from 'react';
import { adminApi } from '@/lib/api';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense } from 'react';
import { useTranslation } from '@/lib/i18n';

export default function AdminLoginPage() {
  return (
    <Suspense fallback={null}>
      <AdminLoginPageInner />
    </Suspense>
  );
}

function AdminLoginPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { t } = useTranslation();
  const [token, setToken] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Whitelist `next` to internal absolute paths only. Without this
  // guard `?next=//evil.com` (or `next=https://evil.com`) made
  // router.push send a freshly-authenticated admin off-site,
  // a textbook phishing primitive.
  const rawNext = searchParams.get('next');
  const next =
    rawNext &&
    rawNext.startsWith('/') &&
    !rawNext.startsWith('//') &&
    !rawNext.startsWith('/\\')
      ? rawNext
      : '/admin/settings';

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await adminApi.login(token.trim());
      router.push(next);
    } catch (e: any) {
      const status = e?.response?.status;
      if (status === 401) setErr(t('admin.login.error_invalid'));
      else if (status === 503) setErr(t('admin.login.error_disabled'));
      else setErr(e?.message ?? 'Failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-md py-12">
      <div className="card">
        <h1 className="mb-2 text-xl font-bold">{t('admin.login.title')}</h1>
        <p className="mb-6 text-sm text-slate-600">{t('admin.login.subtitle')}</p>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="label">{t('admin.login.token')}</label>
            <input
              type="password"
              autoFocus
              value={token}
              onChange={(e) => setToken(e.target.value)}
              className="input-field font-mono"
              placeholder="•••"
            />
          </div>
          {err && (
            <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{err}</div>
          )}
          <button
            type="submit"
            disabled={busy || !token.trim()}
            className="btn-primary w-full disabled:opacity-50"
          >
            {busy ? t('admin.login.busy') : t('admin.login.submit')}
          </button>
        </form>
      </div>
    </div>
  );
}
