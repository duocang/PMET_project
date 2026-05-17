'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { adminApi } from '@/lib/api';
import { useAdminStore } from '@/lib/adminStore';
import { useTranslation } from '@/lib/i18n';
import { SettingsCard } from '@/components/admin/SettingsCard';
import { StatsPanel } from '@/components/admin/StatsPanel';
import { ActivityPanel } from '@/components/admin/ActivityPanel';
import { CleanupCard } from '@/components/admin/CleanupCard';
import { HealthPanel } from '@/components/admin/HealthPanel';
import { DangerZone } from '@/components/admin/DangerZone';

export default function AdminDashboardPage() {
  const router = useRouter();
  const { t } = useTranslation();
  const { isAdmin, checked, reset } = useAdminStore();
  const [loggingOut, setLoggingOut] = useState(false);

  useEffect(() => {
    if (checked && !isAdmin) router.replace('/admin/login?next=/admin');
  }, [checked, isAdmin, router]);

  const logout = async () => {
    setLoggingOut(true);
    try {
      await adminApi.logout();
    } catch {
      // Ignore — cookie may already be gone; we'll reset state anyway.
    }
    reset();
    router.replace('/');
  };

  if (!checked || !isAdmin) {
    return <div className="mx-auto max-w-3xl py-12 text-slate-500">{t('admin.settings.loading')}</div>;
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 py-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">{t('admin.dashboard.title')}</h1>
          <p className="mt-1 text-sm text-slate-500">{t('admin.dashboard.subtitle')}</p>
        </div>
        <button
          onClick={logout}
          disabled={loggingOut}
          className="shrink-0 text-sm text-slate-500 hover:text-slate-700 disabled:opacity-50"
        >
          {loggingOut ? t('admin.dashboard.logout.busy') : t('admin.dashboard.logout')}
        </button>
      </header>

      <section id="stats" className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-500">
          {t('admin.dashboard.section.stats')}
        </h2>
        <StatsPanel />
      </section>

      <section id="activity" className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-500">
          {t('admin.dashboard.section.activity')}
        </h2>
        <ActivityPanel />
      </section>

      <section id="health" className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-500">
          {t('admin.dashboard.section.health')}
        </h2>
        <HealthPanel />
      </section>

      <section id="settings" className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-500">
          {t('admin.dashboard.section.settings')}
        </h2>
        <SettingsCard />
      </section>

      <section id="maintenance" className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-500">
          {t('admin.dashboard.section.maintenance')}
        </h2>
        <CleanupCard />
      </section>

      <section id="danger" className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-500">
          {t('admin.dashboard.section.danger')}
        </h2>
        <DangerZone />
      </section>
    </div>
  );
}
