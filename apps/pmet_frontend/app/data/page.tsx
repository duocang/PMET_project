'use client';

import { useEffect, useState } from 'react';
import { indexingApi, IndexingEntry } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

// Drives the species/DB cards off the live /api/indexing endpoint —
// the same source the submit page's species/motif-db dropdowns use.
// Previously this page hard-coded 6 species with DB names that didn't
// match what was actually on disk (e.g. "JASPAR Plants 2022" vs the
// real `Jaspar_plants_non_redundant_2022` directory). Now whatever's
// installed under data/precomputed_indexes/ is what the user sees, in
// lockstep with what they can actually pick on the submit page.
export default function DataPage() {
  const { t } = useTranslation();
  const [entries, setEntries] = useState<IndexingEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    indexingApi.list()
      .then((res) => setEntries(res.entries))
      .catch(() => setError(t('data.err.failed')))
      .finally(() => setLoading(false));
  }, [t]);

  // Group entries by species, preserving the API's stable alphabetical
  // order. Map keeps insertion order so iteration is deterministic.
  const bySpecies = new Map<string, string[]>();
  for (const e of entries) {
    if (!bySpecies.has(e.species)) bySpecies.set(e.species, []);
    bySpecies.get(e.species)!.push(e.motif_db);
  }

  const humanize = (s: string) => s.replace(/_/g, ' ');

  return (
    <div className="max-w-5xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">{t('data.title')}</h1>

      <div className="card mb-6">
        <h2 className="text-lg font-semibold mb-4">{t('data.heading')}</h2>
        <p className="text-slate-600 mb-2">{t('data.intro')}</p>
        {!loading && !error && (
          <p className="text-sm text-slate-500">
            {t('data.summary')
              .replace('{species}', String(bySpecies.size))
              .replace('{entries}', String(entries.length))}
          </p>
        )}
      </div>

      {loading && (
        <div className="card text-slate-500">{t('data.loading')}</div>
      )}

      {!loading && error && (
        <div className="card text-red-600">{error}</div>
      )}

      {!loading && !error && bySpecies.size === 0 && (
        <div className="card text-slate-500">
          {t('submit.db.empty.before')}
          <code className="mx-1 px-1 bg-slate-100 rounded">make fetch-data</code>
          {t('submit.db.empty.after')}{' '}
          <code className="px-1 bg-slate-100 rounded">data/precomputed_indexes/</code>.
        </div>
      )}

      {!loading && !error && bySpecies.size > 0 && (
        <div className="grid md:grid-cols-2 gap-4">
          {Array.from(bySpecies.entries()).map(([species, dbs]) => (
            <div key={species} className="card">
              <h3 className="font-semibold mb-2 italic">{humanize(species)}</h3>
              <div className="flex flex-wrap gap-2">
                {dbs.map((db) => (
                  <span
                    key={db}
                    className="px-2 py-1 bg-primary-100 text-primary-700 rounded text-sm"
                  >
                    {humanize(db)}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="card mt-6">
        <h2 className="text-lg font-semibold mb-4">{t('data.download.heading')}</h2>
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
    </div>
  );
}
