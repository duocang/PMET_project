'use client';

import { useTranslation } from '@/lib/i18n';

export function LangToggle() {
  const { locale, setLocale, t } = useTranslation();
  const next = locale === 'en' ? 'zh' : 'en';
  return (
    <button
      type="button"
      onClick={() => setLocale(next)}
      aria-label={t('lang.toggle.aria')}
      className="rounded-md px-1.5 py-2 text-xs font-medium text-slate-600 transition-colors hover:bg-slate-100 hover:text-primary-800 sm:px-2.5 sm:text-sm lg:text-base"
    >
      {locale === 'en' ? '汉文' : 'EN'}
    </button>
  );
}
