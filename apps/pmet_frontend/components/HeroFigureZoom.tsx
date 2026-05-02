'use client';

import { useEffect, useState } from 'react';
import { useTranslation } from '@/lib/i18n';

interface Props {
  src: string;
}

export default function HeroFigureZoom({ src }: Props) {
  const [open, setOpen] = useState(false);
  const { t } = useTranslation();
  const alt = t('home.hero.expand_alt');
  const label = t('home.hero.expand_hint');

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
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="hero-zoom-hint group absolute right-4 top-4 z-20 inline-flex items-center gap-1.5 rounded-full border border-white/30 bg-white/10 px-3 py-1.5 text-xs font-semibold text-white backdrop-blur transition hover:scale-105 hover:bg-white/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70"
        aria-label={alt}
      >
        <svg viewBox="0 0 24 24" className="h-4 w-4 transition-transform group-hover:rotate-6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <circle cx="11" cy="11" r="7" />
          <line x1="11" y1="8" x2="11" y2="14" />
          <line x1="8" y1="11" x2="14" y2="11" />
          <line x1="20" y1="20" x2="16.5" y2="16.5" />
        </svg>
        <span>{label}</span>
      </button>

      {open && (
        <div
          onClick={() => setOpen(false)}
          className="zoom-overlay fixed inset-0 z-[60] flex cursor-zoom-out items-center justify-center bg-black/80 p-6 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-label={alt}
        >
          <img
            src={src}
            alt={alt}
            className="zoom-content max-h-full max-w-full rounded bg-white object-contain shadow-2xl"
          />
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); setOpen(false); }}
            className="absolute right-4 top-4 rounded-full bg-white/10 px-3 py-1 text-2xl leading-none text-white hover:bg-white/20"
            aria-label="Close"
          >
            ×
          </button>
        </div>
      )}
    </>
  );
}
