'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import { useTranslation } from '@/lib/i18n';
import { useAdminStore } from '@/lib/adminStore';
import { LangToggle } from './LangToggle';
import type { TranslationKey } from '@/lib/translations';

const GITHUB_URL = 'https://github.com/duocang/PMET_project';

type NavItem = { href: string; key: TranslationKey };

const NAV_ITEMS: NavItem[] = [
  { href: '/', key: 'nav.home' },
  { href: '/submit', key: 'nav.analysis' },
  { href: '/tasks', key: 'nav.tasks' },
  { href: '/visualize', key: 'nav.visualize' },
  { href: '/data', key: 'nav.data' },
  { href: '/about', key: 'nav.about' },
  { href: '/contributors', key: 'nav.contributors' },
];

const NAV_LINK_BASE =
  'inline-flex min-h-[44px] items-center rounded-md px-2.5 text-sm font-medium transition-colors lg:text-base';
const NAV_LINK_IDLE = 'text-slate-600 hover:bg-slate-100 hover:text-primary-800';
const NAV_LINK_ACTIVE = 'bg-primary-50 text-primary-800';

const DRAWER_LINK_BASE =
  'flex min-h-[48px] items-center rounded-md px-4 text-base font-medium transition-colors';

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

function MenuIcon({ open }: { open: boolean }) {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {open ? (
        <>
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </>
      ) : (
        <>
          <line x1="3" y1="6" x2="21" y2="6" />
          <line x1="3" y1="12" x2="21" y2="12" />
          <line x1="3" y1="18" x2="21" y2="18" />
        </>
      )}
    </svg>
  );
}

const ADMIN_NAV_ITEM: NavItem = { href: '/admin', key: 'nav.admin' };

export function NavBar() {
  const { t } = useTranslation();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const isAdmin = useAdminStore((s) => s.isAdmin);
  const navItems = isAdmin ? [...NAV_ITEMS, ADMIN_NAV_ITEM] : NAV_ITEMS;

  const desktopLinkClass = (href: string) =>
    `${NAV_LINK_BASE} ${isActive(pathname, href) ? NAV_LINK_ACTIVE : NAV_LINK_IDLE}`;
  const drawerLinkClass = (href: string) =>
    `${DRAWER_LINK_BASE} ${isActive(pathname, href) ? NAV_LINK_ACTIVE : NAV_LINK_IDLE}`;

  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [open]);

  return (
    <nav className="sticky top-0 z-50 border-b border-hairline bg-white/85 backdrop-blur">
      <div className="page-shell">
        <div className="flex h-16 items-center justify-between gap-3">
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

          {/* Desktop nav */}
          <div className="hidden min-w-0 items-center gap-1 lg:flex xl:gap-1.5">
            {navItems.map((item) => {
              const active = isActive(pathname, item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={desktopLinkClass(item.href)}
                  aria-current={active ? 'page' : undefined}
                >
                  {t(item.key)}
                </Link>
              );
            })}
            <LangToggle />
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="View source on GitHub"
              className="ml-1 inline-flex h-11 w-11 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900"
            >
              <GitHubIcon />
            </a>
          </div>

          {/* Mobile cluster: lang + hamburger */}
          <div className="flex items-center gap-1 lg:hidden">
            <LangToggle />
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="View source on GitHub"
              className="inline-flex h-11 w-11 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900"
            >
              <GitHubIcon />
            </a>
            <button
              type="button"
              onClick={() => setOpen((v) => !v)}
              aria-label={open ? t('nav.menu.close') : t('nav.menu.open')}
              aria-expanded={open}
              aria-controls="mobile-nav-drawer"
              className="inline-flex h-11 w-11 items-center justify-center rounded-md text-slate-700 transition-colors hover:bg-slate-100"
            >
              <MenuIcon open={open} />
            </button>
          </div>
        </div>
      </div>

      {/* Mobile drawer */}
      {open && (
        <>
          <button
            type="button"
            aria-label={t('nav.menu.close')}
            onClick={() => setOpen(false)}
            className="fixed inset-0 z-40 cursor-default bg-slate-900/30 backdrop-blur-sm lg:hidden"
          />
          <div
            id="mobile-nav-drawer"
            className="fixed left-0 right-0 top-16 z-50 border-b border-hairline bg-white shadow-card-hover lg:hidden"
          >
            <div className="page-shell">
              <ul className="flex flex-col gap-1 py-3">
                {navItems.map((item) => {
                  const active = isActive(pathname, item.href);
                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        className={drawerLinkClass(item.href)}
                        aria-current={active ? 'page' : undefined}
                      >
                        {t(item.key)}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          </div>
        </>
      )}
    </nav>
  );
}
