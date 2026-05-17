'use client';

import type { AdminTopError } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

interface Props {
  errors: AdminTopError[];
}

export function TopErrorsTable({ errors }: Props) {
  const { t } = useTranslation();
  if (errors.length === 0) {
    return <div className="text-sm text-slate-500">{t('admin.stats.errors.none')}</div>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
            <th className="py-2 pr-4">{t('admin.stats.errors.col.message')}</th>
            <th className="py-2 pl-4 text-right">{t('admin.stats.errors.col.count')}</th>
          </tr>
        </thead>
        <tbody>
          {errors.map((e, i) => (
            <tr key={i} className="border-b border-slate-100">
              <td className="py-2 pr-4 font-mono text-xs text-slate-700">{e.message}</td>
              <td className="py-2 pl-4 text-right font-medium text-slate-900">{e.count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
