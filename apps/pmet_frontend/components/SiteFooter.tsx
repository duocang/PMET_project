'use client';

import Link from 'next/link';
import { useTranslation } from '@/lib/i18n';

const GITHUB_URL = 'https://github.com/duocang/PMET_project';

export function SiteFooter() {
  const { t } = useTranslation();
  return (
    <footer
      role="contentinfo"
      className="mt-16 border-t border-hairline bg-white/60 text-sm text-slate-500"
    >
      <div className="page-shell py-8">
        <div className="flex flex-col items-center gap-3 text-center sm:flex-row sm:justify-between sm:text-left">
          <div className="space-y-1">
            <p className="font-medium text-slate-600">{t('footer.text')}</p>
            <p className="text-slate-500">{t('footer.maintainer')}</p>
          </div>
          <nav aria-label={t('footer.linksAria')} className="flex flex-wrap items-center justify-center gap-x-5 gap-y-1">
            <Link href="/about" className="hover:text-primary-700">
              {t('nav.about')}
            </Link>
            <Link href="/contributors" className="hover:text-primary-700">
              {t('nav.contributors')}
            </Link>
            <Link href="/impressum" className="hover:text-primary-700">
              Impressum
            </Link>
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-primary-700"
            >
              GitHub
            </a>
          </nav>
        </div>
      </div>
    </footer>
  );
}
