'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useTranslation } from '@/lib/i18n';
import { LangToggle } from './LangToggle';

const GITHUB_URL = 'https://github.com/duocang/PMET_project';

const NAV_LINK_BASE =
  'rounded-md px-1.5 py-2 text-xs font-medium transition-colors sm:px-2.5 sm:text-sm lg:text-base';
const NAV_LINK_IDLE = 'text-slate-600 hover:bg-slate-100 hover:text-primary-800';
const NAV_LINK_ACTIVE = 'bg-primary-50 text-primary-800';

function isActive(pathname: string | null, href: string) {
  if (!pathname) return false;
  if (href === '/') return pathname === '/';
  return pathname === href || pathname.startsWith(`${href}/`);
}

function GitHubIcon() {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
      className="gh-icon"
    >
      <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
    </svg>
  );
}

export function NavBar() {
  const { t } = useTranslation();
  const pathname = usePathname();
  const linkClass = (href: string) =>
    `${NAV_LINK_BASE} ${isActive(pathname, href) ? NAV_LINK_ACTIVE : NAV_LINK_IDLE}`;
  return (
    <nav className="sticky top-0 z-50 border-b border-hairline bg-white/85 backdrop-blur">
      <div className="page-shell">
        <div className="flex h-16 items-center justify-between">
          <Link href="/" className="flex min-w-0 items-center group" aria-label="PMET home">
            <img
              src="/figures/logo_small.png"
              alt="PMET"
              className="h-9 w-auto shrink-0 transition-transform group-hover:scale-105"
            />
            <span className="ml-3 hidden truncate text-sm font-medium text-slate-500 md:inline">
              {t('nav.tagline')}
            </span>
          </Link>
          <div className="flex min-w-0 items-center gap-1 sm:gap-2 lg:gap-3">
            <Link href="/" className={linkClass('/')}>
              {t('nav.home')}
            </Link>
            <Link href="/submit" className={linkClass('/submit')}>
              {t('nav.analysis')}
            </Link>
            <Link href="/tasks" className={linkClass('/tasks')}>
              {t('nav.tasks')}
            </Link>
            <Link href="/visualize" className={linkClass('/visualize')}>
              {t('nav.visualize')}
            </Link>
            <Link href="/data" className={linkClass('/data')}>
              {t('nav.data')}
            </Link>
            <Link href="/about" className={linkClass('/about')}>
              {t('nav.about')}
            </Link>
            <Link href="/contributors" className={linkClass('/contributors')}>
              {t('nav.contributors')}
            </Link>
            <LangToggle />
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="View source on GitHub"
              className="ml-0 rounded-md p-1.5 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 sm:ml-1 sm:p-2"
            >
              <GitHubIcon />
            </a>
          </div>
        </div>
      </div>
    </nav>
  );
}
