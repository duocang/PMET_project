'use client';

import Link from 'next/link';
import { useTranslation } from '@/lib/i18n';
import { TranslationKey } from '@/lib/translations';
import ZoomableImage from '@/components/ZoomableImage';
import HeroFigureZoom from '@/components/HeroFigureZoom';

function DatabaseIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <ellipse cx="12" cy="5" rx="7" ry="3" />
      <path d="M5 5v6c0 1.7 3.1 3 7 3s7-1.3 7-3V5" />
      <path d="M5 11v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6" />
    </svg>
  );
}

function GenomeIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M7 3c6 2 10 6 10 18" />
      <path d="M17 3C11 5 7 9 7 21" />
      <path d="M8.5 6.5h7" />
      <path d="M7.5 10.5h9" />
      <path d="M7.5 14.5h9" />
      <path d="M8.5 18.5h7" />
    </svg>
  );
}

function IntervalIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M4 7h16" />
      <path d="M4 17h16" />
      <path d="M7 7v10" />
      <path d="M17 7v10" />
      <path d="M10 12h4" />
    </svg>
  );
}

function ChartIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M4 19V5" />
      <path d="M4 19h16" />
      <rect x="7" y="10" width="3" height="6" rx="1" />
      <rect x="12" y="7" width="3" height="9" rx="1" />
      <rect x="17" y="12" width="3" height="4" rx="1" />
    </svg>
  );
}

interface ModeDef {
  titleKey: TranslationKey;
  descKey: TranslationKey;
  actionKey: TranslationKey;
  href: string;
  icon: JSX.Element;
}

const modes: ModeDef[] = [
  {
    titleKey: 'home.mode.promoters_pre.title',
    descKey: 'home.mode.promoters_pre.desc',
    actionKey: 'home.mode.promoters_pre.action',
    href: '/submit?mode=promoters_pre',
    icon: <DatabaseIcon />,
  },
  {
    titleKey: 'home.mode.promoters.title',
    descKey: 'home.mode.promoters.desc',
    actionKey: 'home.mode.promoters.action',
    href: '/submit?mode=promoters',
    icon: <GenomeIcon />,
  },
  {
    titleKey: 'home.mode.intervals.title',
    descKey: 'home.mode.intervals.desc',
    actionKey: 'home.mode.intervals.action',
    href: '/submit?mode=intervals',
    icon: <IntervalIcon />,
  },
  {
    titleKey: 'home.mode.visualize.title',
    descKey: 'home.mode.visualize.desc',
    actionKey: 'home.mode.visualize.action',
    href: '/visualize',
    icon: <ChartIcon />,
  },
];

interface StepDef {
  n: string;
  titleKey: TranslationKey;
  descKey: TranslationKey;
}

const steps: StepDef[] = [
  { n: '01', titleKey: 'home.how.step1.title', descKey: 'home.how.step1.desc' },
  { n: '02', titleKey: 'home.how.step2.title', descKey: 'home.how.step2.desc' },
  { n: '03', titleKey: 'home.how.step3.title', descKey: 'home.how.step3.desc' },
  { n: '04', titleKey: 'home.how.step4.title', descKey: 'home.how.step4.desc' },
];

export default function HomePage() {
  const { t, locale } = useTranslation();
  const langSuffix = locale === 'zh' ? 'cn' : 'en';

  return (
    <div className="space-y-16 pb-14">
      <section className="hero-stage">
        <HeroFigureZoom src="/figures/pmet-hero-bg.svg" />
        <div className="hero-content">
          <p className="mb-4 text-xs font-bold uppercase tracking-[0.22em] text-teal-100">{t('home.hero.eyebrow')}</p>
          <h1 className="text-5xl font-bold leading-tight text-white md:text-6xl">PMET</h1>
          <p className="mt-4 max-w-2xl text-lg leading-8 text-teal-50 md:text-xl">{t('home.hero.tagline')}</p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link href="/submit?mode=promoters_pre" className="btn-primary w-48">
              {t('home.hero.cta_primary')}
            </Link>
            <Link href="/visualize" className="btn-secondary w-48">
              {t('home.hero.cta_secondary')}
            </Link>
          </div>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link
              href="/data#species"
              className="w-40 rounded-lg border border-white/15 bg-white/10 px-5 py-3 text-white backdrop-blur transition hover:bg-white/20 hover:border-white/30"
            >
              <div className="text-2xl font-bold leading-none">23</div>
              <div className="mt-1.5 text-xs text-teal-50">{t('home.hero.stat_species')}</div>
            </Link>
            <Link
              href="/data#motif-databases"
              className="w-40 rounded-lg border border-white/15 bg-white/10 px-5 py-3 text-white backdrop-blur transition hover:bg-white/20 hover:border-white/30"
            >
              <div className="text-2xl font-bold leading-none">6</div>
              <div className="mt-1.5 text-xs text-teal-50">{t('home.hero.stat_dbs')}</div>
            </Link>
          </div>
        </div>
      </section>

      <section id="modes" className="scroll-mt-24">
        <div className="mb-8 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="eyebrow mb-2">{t('home.modes.eyebrow')}</p>
            <h2 className="section-heading">{t('home.modes.heading')}</h2>
          </div>
          <p className="max-w-2xl text-slate-600">{t('home.modes.summary')}</p>
        </div>

        <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">
          {modes.map((mode) => (
            <div key={mode.titleKey} className="mode-card group">
              <div className="mode-icon">{mode.icon}</div>
              <h3 className="text-lg font-semibold text-slate-950">{t(mode.titleKey)}</h3>
              <p className="mt-3 flex-1 text-sm leading-6 text-slate-600">{t(mode.descKey)}</p>
              <Link href={mode.href} className="btn-primary mt-6 w-full">
                {t(mode.actionKey)}
              </Link>
            </div>
          ))}
        </div>
      </section>

      <section id="how-it-works" className="scroll-mt-24">
        <div className="card">
          <div className="mb-8 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
            <div>
              <p className="eyebrow mb-2">{t('home.how.eyebrow')}</p>
              <h2 className="section-heading">{t('home.how.heading')}</h2>
            </div>
            <Link href="/tasks" className="font-semibold text-primary-700 hover:text-primary-900">
              {t('home.how.viewtasks')}
            </Link>
          </div>

          <div className="grid gap-4 md:grid-cols-4">
            {steps.map((step) => (
              <div key={step.n} className="rounded-lg border border-slate-200 bg-slate-50/80 p-4">
                <div className="mb-4 inline-flex rounded-md bg-white px-2.5 py-1 text-xs font-bold text-primary-700 shadow-sm">{step.n}</div>
                <h3 className="font-semibold text-slate-950">{t(step.titleKey)}</h3>
                <p className="mt-2 text-sm leading-6 text-slate-600">{t(step.descKey)}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="learn-more" className="scroll-mt-24">
        <div className="mb-8">
          <p className="eyebrow mb-2">{t('home.learn.eyebrow')}</p>
          <h2 className="section-heading">{t('home.learn.heading')}</h2>
        </div>

        <div className="space-y-4">
          <details className="card group" open>
            <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-semibold text-slate-950">
              <span>{t('home.learn.what.title')}</span>
              <span className="text-slate-400 transition-transform group-open:rotate-180">▾</span>
            </summary>
            <div className="mt-6 space-y-5">
              <p className="leading-7 text-slate-600">{t('home.learn.what.intro')}</p>
              <ul className="list-disc space-y-2 pl-6 text-slate-600 marker:text-primary-600">
                <li>{t('home.learn.what.bullet1')}</li>
                <li>{t('home.learn.what.bullet2')}</li>
                <li>{t('home.learn.what.bullet3')}</li>
                <li>{t('home.learn.what.bullet4')}</li>
              </ul>
              <ZoomableImage
                src={`/figures/pmet-promoter-pair-enrichment-${langSuffix}.svg`}
                alt={t('home.learn.what.alt')}
                className="w-full rounded-lg border border-slate-200 bg-white"
              />
              <p className="text-center text-sm text-slate-500">{t('home.learn.what.caption')}</p>
            </div>
          </details>

          <details className="card group">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-semibold text-slate-950">
              <span>{t('home.learn.workflow.title')}</span>
              <span className="text-slate-400 transition-transform group-open:rotate-180">▾</span>
            </summary>
            <div className="mt-6 space-y-5">
              <p className="leading-7 text-slate-600">{t('home.learn.workflow.intro')}</p>
              <ul className="list-disc space-y-2 pl-6 text-slate-600 marker:text-primary-600">
                <li>{t('home.learn.workflow.bullet1')}</li>
                <li>{t('home.learn.workflow.bullet2')}</li>
              </ul>
              <ZoomableImage
                src={`/figures/algorithm-two-stages-${langSuffix}.svg`}
                alt={t('home.learn.workflow.alt')}
                className="w-full rounded-lg border border-slate-200 bg-white"
              />
              <p className="text-center text-sm text-slate-500">{t('home.learn.workflow.caption')}</p>
            </div>
          </details>

          <details className="card group">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-semibold text-slate-950">
              <span>{t('home.learn.modes.title')}</span>
              <span className="text-slate-400 transition-transform group-open:rotate-180">▾</span>
            </summary>
            <div className="mt-6 space-y-5">
              <p className="leading-7 text-slate-600">{t('home.learn.modes.intro')}</p>
              <ul className="list-disc space-y-2 pl-6 text-slate-600 marker:text-primary-600">
                <li>{t('home.learn.modes.bullet1')}</li>
                <li>{t('home.learn.modes.bullet2')}</li>
                <li>{t('home.learn.modes.bullet3')}</li>
                <li>{t('home.learn.modes.bullet4')}</li>
              </ul>
              <ZoomableImage
                src={`/figures/workflow-overview-${langSuffix}.svg`}
                alt={t('home.learn.modes.alt')}
                className="w-full rounded-lg border border-slate-200 bg-white"
              />
              <p className="text-center text-sm text-slate-500">{t('home.learn.modes.caption')}</p>
            </div>
          </details>
        </div>
      </section>
    </div>
  );
}
