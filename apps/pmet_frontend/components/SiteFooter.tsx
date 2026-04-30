'use client';

import { useTranslation } from '@/lib/i18n';

const GITHUB_URL = 'https://github.com/duocang/PMET_project';

export function SiteFooter() {
  const { t } = useTranslation();
  return (
    <footer className="mt-16 border-t border-slate-200/80 bg-white/60 py-8 text-center text-sm text-slate-500">
      <p>
        {t('footer.text')} ·{' '}
        <a
          href={GITHUB_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="hover:text-primary-700"
        >
          GitHub
        </a>
      </p>
      <p className="mt-1">{t('footer.maintainer')}</p>
    </footer>
  );
}
