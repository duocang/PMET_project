'use client';

import { useTranslation } from '@/lib/i18n';
import type { TranslationKey } from '@/lib/translations';

// Single source of truth for the contributor list. Edit this array to
// add / remove people; the JSX renders one card per entry.
//
// Display order: the developer is listed first as the page maintainer;
// other contributors follow, sorted alphabetically by surname.
//
// Naming convention: ``nameEn`` follows "[Prof. ]Dr. Surname, Given".
// ``nameZh`` is optional and only set when the contributor has a
// Chinese name they want shown in the cn locale; for everyone else the
// cn locale falls back to ``nameEn``.
interface Contributor {
  nameEn: string;
  nameZh?: string;
  /** Translation keys for this person's role(s). Multiple roles render
   *  joined by " · " on the card. */
  roleKeys: TranslationKey[];
  affiliation?: string;
  email?: string;
  homepage?: string;
}

const CONTRIBUTORS: Contributor[] = [
  {
    nameEn: 'Dr. Wang, Xuesong',
    nameZh: '王雪松',
    roleKeys: [
      'contributors.role.developer',
      'contributors.role.researcher',
      'contributors.role.maintainer',
    ],
    email: 'wang23@uni-muesnter.de',
    homepage: 'https://www.uni-giessen.de/de/fbz/fb09/institute/phyto/mitarbeiter/phd/wang',
  },
  {
    nameEn: 'Dr. Brown, Paul',
    roleKeys: ['contributors.role.developer', 'contributors.role.researcher'],
    email: 'p.e.brown@warwick.ac.uk',
    homepage: 'https://warwick.ac.uk/fac/cross_fac/zeeman_institute/staffv2/paulbrown/',
  },
  {
    nameEn: 'Prof. Dr. Ott, Sascha',
    roleKeys: ['contributors.role.pi'],
    email: 's.ott@warwick.ac.uk',
    homepage: 'https://warwick.ac.uk/fac/cross_fac/zeeman_institute/staffv2/sascha_ott/',
  },
  {
    nameEn: 'Prof. Dr. Schäfer, Patrick',
    roleKeys: ['contributors.role.pi'],
    email: 'Patrick.Schaefer@agrar.uni-giessen.de',
    homepage: 'https://www.uni-giessen.de/de/fbz/fb09/institute/phyto/mitarbeiter/leitung/schaefer-p',
  },
  {
    nameEn: 'Dr. Woolley-Allen, Kate',
    roleKeys: ['contributors.role.researcher'],
    email: 'k.woolley-allen@warwick.ac.uk',
    homepage: 'https://warwick.ac.uk/fac/sci/sbdtc/people/students/2012/kate_allen/',
  },
];

function MailIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="2" y="4" width="20" height="16" rx="2" />
      <path d="M22 6l-10 7L2 6" />
    </svg>
  );
}

function GlobeIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="10" />
      <path d="M2 12h20" />
      <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
    </svg>
  );
}

export default function ContributorsPage() {
  const { t, locale } = useTranslation();
  return (
    <div className="max-w-5xl mx-auto">
      <h1 className="text-2xl font-bold mb-2">{t('contributors.title')}</h1>
      <p className="mb-6 text-slate-600">{t('contributors.intro')}</p>

      <div className="grid md:grid-cols-2 gap-4">
        {CONTRIBUTORS.map((c) => {
          const displayName = locale === 'zh' && c.nameZh ? c.nameZh : c.nameEn;
          return (
            <div key={c.nameEn} className="card">
              <h3 className="font-semibold text-slate-900">{displayName}</h3>
              <p className="text-sm text-primary-700">
                {c.roleKeys.map((k) => t(k)).join(' · ')}
              </p>
              {c.affiliation && (
                <p className="mt-1 text-sm text-slate-600">{c.affiliation}</p>
              )}
              {(c.email || c.homepage) && (
                <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-sm">
                  {c.email && (
                    <a
                      href={`mailto:${c.email}`}
                      className="inline-flex items-center gap-1 text-primary-700 hover:underline break-all"
                    >
                      <MailIcon />
                      {c.email}
                    </a>
                  )}
                  {c.homepage && (
                    <a
                      href={c.homepage}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-slate-700 hover:underline"
                    >
                      <GlobeIcon />
                      {t('contributors.homepage')}
                    </a>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <p className="mt-6 text-sm text-slate-500">{t('contributors.contributing_note')}</p>
    </div>
  );
}
