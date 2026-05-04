'use client';

import { useEffect, useState } from 'react';
import { indexingApi, GenomeCatalogEntry, MotifDbCatalogEntry } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';
import type { TranslationKey } from '@/lib/translations';

// Lengths beyond which the species description is collapsed behind a
// "show more" toggle. Picked so a single sentence stays visible without
// wrapping more than 2-3 lines on a typical card width.
const DESCRIPTION_PREVIEW_CHARS = 140;

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function SpeciesCard({ entry, t }: { entry: GenomeCatalogEntry; t: (key: TranslationKey) => string }) {
  const [expanded, setExpanded] = useState(false);
  const desc = entry.description ?? '';
  const needsToggle = desc.length > DESCRIPTION_PREVIEW_CHARS;
  const shown = !needsToggle || expanded ? desc : `${desc.slice(0, DESCRIPTION_PREVIEW_CHARS).trimEnd()}…`;

  return (
    <div className="card">
      <h3 className="font-semibold mb-2 italic">{entry.humanized}</h3>
      {desc && (
        <p className="text-sm text-slate-600 mb-3 leading-relaxed">
          {shown}
          {needsToggle && (
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="ml-1 text-primary-700 hover:underline"
            >
              {expanded ? t('data.species.collapse') : t('data.species.expand')}
            </button>
          )}
        </p>
      )}
      <dl className="text-sm space-y-1">
        {entry.genome_name && (
          <div className="flex gap-2">
            <dt className="text-slate-500 shrink-0">{t('data.species.genome')}</dt>
            <dd className="text-slate-700 break-all">
              {entry.genome_link ? (
                <a
                  href={entry.genome_link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary-700 hover:underline"
                >
                  {entry.genome_name}
                </a>
              ) : (
                entry.genome_name
              )}
            </dd>
          </div>
        )}
        {entry.annotation_name && (
          <div className="flex gap-2">
            <dt className="text-slate-500 shrink-0">{t('data.species.annotation')}</dt>
            <dd className="text-slate-700 break-all">
              {entry.annotation_link ? (
                <a
                  href={entry.annotation_link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary-700 hover:underline"
                >
                  {entry.annotation_name}
                </a>
              ) : (
                entry.annotation_name
              )}
            </dd>
          </div>
        )}
      </dl>
    </div>
  );
}

export default function DataPage() {
  const { t } = useTranslation();
  const [species, setSpecies] = useState<GenomeCatalogEntry[]>([]);
  const [databases, setDatabases] = useState<MotifDbCatalogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([indexingApi.genomes(), indexingApi.motifDatabases()])
      .then(([g, m]) => {
        setSpecies(g.species);
        setDatabases(m.databases);
      })
      .catch(() => setError(t('data.err.failed')))
      .finally(() => setLoading(false));
  }, [t]);

  // Re-scroll to the URL hash once content has settled. The browser's
  // initial anchor jump happens before species/databases finish loading,
  // so it lands at the wrong y-offset. Re-issue the scroll after the
  // first paint that includes the data.
  useEffect(() => {
    if (loading) return;
    const hash = window.location.hash.slice(1);
    if (!hash) return;
    requestAnimationFrame(() => {
      document.getElementById(hash)?.scrollIntoView({ block: 'start' });
    });
  }, [loading]);

  return (
    <div className="max-w-5xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">{t('data.title')}</h1>

      {/* Download moved to the top so visitors see the bulk-download path
          before scrolling through the catalogs. */}
      <div className="card mb-8">
        <h2 className="text-lg font-semibold mb-2">{t('data.download.heading')}</h2>
        <p className="text-slate-600 mb-4">{t('data.download.intro')}</p>
        <a
          href="https://zenodo.org/record/8435321"
          target="_blank"
          rel="noopener noreferrer"
          className="btn-primary inline-block"
        >
          {t('data.download.button')}
        </a>
      </div>

      {loading && <div className="card text-slate-500">{t('data.loading')}</div>}
      {!loading && error && <div className="card text-red-600">{error}</div>}

      {!loading && !error && (
        <>
          <section id="motif-databases" className="scroll-mt-24 mb-8">
            <h2 className="text-lg font-semibold mb-1">{t('data.motif.heading')}</h2>
            <p className="text-sm text-slate-500 mb-4">
              {t('data.motif.intro').replace('{count}', String(databases.length))}
            </p>
            <div className="grid md:grid-cols-2 gap-4">
              {databases.map((db) => (
                <div key={db.name} className="card">
                  <h3 className="font-semibold mb-2">{db.humanized}</h3>
                  <dl className="text-sm space-y-1">
                    <div className="flex gap-2">
                      <dt className="text-slate-500 shrink-0">{t('data.motif.source')}</dt>
                      <dd className="text-slate-700 break-all">
                        {db.source_link ? (
                          <a
                            href={db.source_link}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-primary-700 hover:underline"
                          >
                            {db.source_link}
                          </a>
                        ) : (
                          <span className="text-slate-400">{t('data.motif.no_link')}</span>
                        )}
                      </dd>
                    </div>
                    <div className="flex gap-2">
                      <dt className="text-slate-500 shrink-0">{t('data.motif.download')}</dt>
                      <dd className="text-slate-700 break-all">
                        {db.local_file ? (
                          <a
                            href={`/api/indexing/motif-databases/${encodeURIComponent(db.name)}/file`}
                            className="text-primary-700 hover:underline"
                            download={db.local_file.filename}
                          >
                            {db.local_file.filename}{' '}
                            <span className="text-slate-500">({formatBytes(db.local_file.size_bytes)})</span>
                          </a>
                        ) : (
                          <span className="text-slate-400">{t('data.motif.no_file')}</span>
                        )}
                      </dd>
                    </div>
                  </dl>
                </div>
              ))}
            </div>
          </section>

          <section id="species" className="scroll-mt-24">
            <h2 className="text-lg font-semibold mb-1">{t('data.species.heading')}</h2>
            <p className="text-sm text-slate-500 mb-4">
              {t('data.species.intro').replace('{count}', String(species.length))}
            </p>
            <div className="grid md:grid-cols-2 gap-4">
              {species.map((entry) => (
                <SpeciesCard key={entry.name} entry={entry} t={t} />
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
