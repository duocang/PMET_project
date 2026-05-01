'use client';

import { useState, useEffect, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import toast from 'react-hot-toast';
import FileUpload from '@/components/FileUpload';
import ParameterPanel from '@/components/ParameterPanel';
import {
  EXAMPLE_FASTA,
  EXAMPLE_GFF3,
  EXAMPLE_MEME,
  EXAMPLE_GENE_LIST,
  EXAMPLE_PEAK_LIST,
} from '@/lib/fileExamples';
import { AnalysisMode, EstimateResponse } from '@/lib/types';
import {
  taskApi,
  fileApi,
  indexingApi,
  IndexingEntry,
  IndexingSpeciesDetail,
  IndexingMotifDbDetail,
} from '@/lib/api';
import { useSettingsStore, useTaskStore } from '@/lib/store';
import { useTranslation } from '@/lib/i18n';
import type { TranslationKey } from '@/lib/translations';
import { formatRuntimeRange } from '@/lib/runtime';

function SubmitPageContent() {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const urlMode = searchParams.get('mode') as AnalysisMode | null;

  // Form state lives in the settings store (in-memory) so it survives
  // SPA navigation — leaving /submit and coming back used to clear
  // species / motif-DB / file picks because the page-level useState
  // unmounted with the route. Only `mode` reaches localStorage; the
  // rest stays in-memory.
  const {
    mode, setMode, email, setEmail,
    filesByMode, pathsByMode, speciesByMode, paramsByMode,
    updateFilesForMode, updatePathsForMode, setSpeciesForMode, updateParamsForMode,
  } = useSettingsStore();
  const { setLoading, addTask } = useTaskStore();

  // params live in the store so the user's per-mode tweaks (IC,
  // promoter_length, etc.) survive nav the same way species and
  // file picks do. Initial defaults live in lib/store.ts.
  const params = paramsByMode[mode];
  const setParams = (next: typeof params | ((prev: typeof params) => typeof params)) => {
    if (typeof next === 'function') {
      updateParamsForMode(mode, next(params));
    } else {
      updateParamsForMode(mode, next);
    }
  };

  type FileFieldType = 'genes' | 'fasta' | 'gff3' | 'meme';

  const files = filesByMode[mode];
  const uploadedPaths = pathsByMode[mode];
  const selectedSpecies = speciesByMode[mode];

  const updateFiles = (patch: Partial<typeof files>) => updateFilesForMode(mode, patch);
  const updatePaths = (patch: Partial<typeof uploadedPaths>) => updatePathsForMode(mode, patch);
  const setSelectedSpecies = (v: string) => setSpeciesForMode(mode, v);

  const [submitting, setSubmitting] = useState(false);
  const [indexingEntries, setIndexingEntries] = useState<IndexingEntry[]>([]);

  // Runtime estimate. Recomputed (debounced ~400 ms) whenever the inputs
  // that affect duration change — mode, uploaded file paths, premade
  // index pick. Backend reads the file paths to count motifs / genes /
  // fasta size; we only ship paths so the form stays cheap.
  const [estimate, setEstimate] = useState<EstimateResponse | null>(null);
  const [estimateLoading, setEstimateLoading] = useState(false);

  // Single per-page-mount upload session id. Every file upload from this
  // page reuses this id so all four files for one submission land in the
  // same temp dir under results/app/uploads/<id>/, instead of each upload
  // racing for its own timestamped temp_<...> dir.
  // 12 hex chars (~48 bits) is plenty for collision-free task IDs at this
  // scale and keeps URLs short. Total length: pmet_ (5) + 12 = 17.
  const [uploadSessionId] = useState(() => {
    const rand =
      typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
        ? crypto.randomUUID().replace(/-/g, '').slice(0, 12)
        : `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
    return `pmet_${rand}`;
  });

  // Detail panel state — only used in promoters_pre. Species and motif-DB
  // details are fetched independently so the species block can render as
  // soon as a species is picked, without waiting for the motif database.
  const [detailOpen, setDetailOpen] = useState(false);
  const [speciesCache, setSpeciesCache] = useState<Record<string, IndexingSpeciesDetail>>({});
  const [motifDbCache, setMotifDbCache] = useState<Record<string, IndexingMotifDbDetail>>({});
  const [speciesLoading, setSpeciesLoading] = useState(false);
  const [motifDbLoading, setMotifDbLoading] = useState(false);

  const humanize = (s: string) => s.replace(/_/g, ' ');
  const speciesList = Array.from(new Set(indexingEntries.map((e) => e.species)));
  const motifDbOptions = indexingEntries.filter((e) => e.species === selectedSpecies);

  useEffect(() => {
    if (urlMode) setMode(urlMode);
  }, [urlMode, setMode]);

  // Populate the pre-computed database dropdown from whatever is actually
  // installed under data/precomputed_indexes/ on the server.
  useEffect(() => {
    if (mode !== 'promoters_pre') return;
    indexingApi.list()
      .then((res) => setIndexingEntries(res.entries))
      .catch((err) => console.error('Failed to load indexing list', err));
  }, [mode]);

  // Recompute the runtime estimate (debounced 400 ms) whenever any input
  // that affects duration changes — uploaded paths, premade index pick,
  // mode. Guarded: only fire when there's at least *something* to
  // estimate against, to avoid showing "5 – 10 seconds" before the user
  // has supplied any inputs.
  useEffect(() => {
    const hasInputs =
      (mode === 'promoters_pre' && (files.premade_index || uploadedPaths.genes)) ||
      (mode === 'intervals' && (uploadedPaths.fasta || uploadedPaths.meme)) ||
      (mode === 'promoters' && (uploadedPaths.fasta || uploadedPaths.meme));
    if (!hasInputs) {
      setEstimate(null);
      return;
    }

    setEstimateLoading(true);
    // Cancel an in-flight request when inputs change so a slow earlier
    // response can't overwrite a fresher one.
    const controller = new AbortController();
    const handle = setTimeout(() => {
      taskApi
        .estimate(
          {
            mode,
            genes_file: uploadedPaths.genes || undefined,
            fasta_file: uploadedPaths.fasta || undefined,
            meme_file: uploadedPaths.meme || undefined,
            premade_index: files.premade_index || undefined,
          },
          controller.signal,
        )
        .then((r) => setEstimate(r))
        .catch((err) => {
          if (err?.name === 'CanceledError' || err?.code === 'ERR_CANCELED') {
            // Superseded by a newer request; ignore silently.
            return;
          }
          console.error('estimate failed', err);
          setEstimate(null);
        })
        .finally(() => {
          if (!controller.signal.aborted) setEstimateLoading(false);
        });
    }, 400);

    return () => {
      clearTimeout(handle);
      controller.abort();
      setEstimateLoading(false);
    };
  }, [
    mode,
    uploadedPaths.genes,
    uploadedPaths.fasta,
    uploadedPaths.meme,
    files.premade_index,
  ]);

  // Lazy-fetch species and motif-db detail independently when the user
  // opens the panel. Each has its own cache so species info appears the
  // moment a species is picked, without waiting for the motif database.
  const selectedEntry = indexingEntries.find((e) => e.value === files.premade_index);
  const motifDbKey = selectedEntry ? `${selectedEntry.species}/${selectedEntry.motif_db}` : '';
  const currentSpecies = selectedSpecies ? speciesCache[selectedSpecies] : undefined;
  const currentMotifDb = motifDbKey ? motifDbCache[motifDbKey] : undefined;

  useEffect(() => {
    if (!detailOpen || !selectedSpecies || currentSpecies) return;
    setSpeciesLoading(true);
    indexingApi.speciesDetail(selectedSpecies)
      .then((d) => setSpeciesCache((prev) => ({ ...prev, [selectedSpecies]: d.species })))
      .catch((err) => console.error('Failed to load species detail', err))
      .finally(() => setSpeciesLoading(false));
  }, [detailOpen, selectedSpecies, currentSpecies]);

  useEffect(() => {
    if (!detailOpen || !selectedEntry || currentMotifDb) return;
    setMotifDbLoading(true);
    indexingApi.motifDbDetail(selectedEntry.species, selectedEntry.motif_db)
      .then((d) => setMotifDbCache((prev) => ({ ...prev, [motifDbKey]: d.motif_db })))
      .catch((err) => console.error('Failed to load motif_db detail', err))
      .finally(() => setMotifDbLoading(false));
  }, [detailOpen, motifDbKey, selectedEntry, currentMotifDb]);

  const handleFileUpload = async (
    file: File,
    fileType: FileFieldType,
    onProgress?: (pct: number) => void
  ) => {
    try {
      const result = await fileApi.upload(file, fileType, uploadSessionId, onProgress);
      updatePaths({ [fileType]: result.path });
      updateFiles({ [fileType]: file });
    } catch (error) {
      throw error;
    }
  };

  const handleFileClear = async (fileType: FileFieldType) => {
    const path = uploadedPaths[fileType];
    if (path) {
      // Best-effort: even if server delete fails, clear the local state so
      // the user can re-pick. The toast inside FileUpload surfaces any
      // server-side failure.
      try { await fileApi.deleteUpload(path); }
      finally {
        updatePaths({ [fileType]: '' });
        updateFiles({ [fileType]: null });
      }
    } else {
      updateFiles({ [fileType]: null });
    }
  };

  const handleParamChange = (newParams: Record<string, any>) => {
    setParams((prev) => ({ ...prev, ...newParams }));
  };

  const validateForm = (): boolean => {
    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      toast.error(t('submit.toast.invalid_email'));
      return false;
    }

    if (!uploadedPaths.genes && !files.genes) {
      toast.error(t('submit.toast.upload_genes'));
      return false;
    }

    if (mode === 'promoters') {
      if (!uploadedPaths.fasta && !files.fasta) {
        toast.error(t('submit.toast.upload_genome'));
        return false;
      }
      if (!uploadedPaths.gff3 && !files.gff3) {
        toast.error(t('submit.toast.upload_annotation'));
        return false;
      }
      if (!uploadedPaths.meme && !files.meme) {
        toast.error(t('submit.toast.upload_motif'));
        return false;
      }
    }

    if (mode === 'intervals') {
      if (!uploadedPaths.fasta && !files.fasta) {
        toast.error(t('submit.toast.upload_genome'));
        return false;
      }
      if (!uploadedPaths.meme && !files.meme) {
        toast.error(t('submit.toast.upload_motif'));
        return false;
      }
    }

    if (mode === 'promoters_pre' && !files.premade_index) {
      toast.error(t('submit.toast.pick_db'));
      return false;
    }

    return true;
  };

  const handleSubmit = async () => {
    if (!validateForm()) return;

    setSubmitting(true);
    setLoading(true);

    try {
      // Upload files first
      let genesPath = uploadedPaths.genes;
      if (files.genes && !genesPath) {
        const result = await fileApi.upload(files.genes, 'genes', uploadSessionId);
        genesPath = result.path;
      }

      let fastaPath = uploadedPaths.fasta;
      let gff3Path = uploadedPaths.gff3;
      let memePath = uploadedPaths.meme;

      if (mode !== 'promoters_pre') {
        if (files.fasta && !fastaPath) {
          const result = await fileApi.upload(files.fasta, 'fasta', uploadSessionId);
          fastaPath = result.path;
        }
        if (files.gff3 && !gff3Path && mode === 'promoters') {
          const result = await fileApi.upload(files.gff3, 'gff3', uploadSessionId);
          gff3Path = result.path;
        }
        if (files.meme && !memePath) {
          const result = await fileApi.upload(files.meme, 'meme', uploadSessionId);
          memePath = result.path;
        }
      }

      // In promoters_pre, fixedParams represents what the index was built
      // with — override any stale values carried over from other modes so
      // the backend gets the real build-time settings.
      const selectedFixed = indexingEntries.find((e) => e.value === files.premade_index)?.fixed_params;
      const effectiveParams = mode === 'promoters_pre' && selectedFixed
        ? { ...params, ...selectedFixed }
        : params;

      // Create task. Reuse the upload session id so the run inherits the
      // same results/app/<id>/ root that already holds upload/.
      const taskData = {
        email,
        mode,
        task_id: uploadSessionId,
        ...effectiveParams,
        genes_file: genesPath,
        fasta_file: fastaPath || undefined,
        gff3_file: gff3Path || undefined,
        meme_file: memePath || undefined,
        premade_index: files.premade_index || undefined,
      };

      const task = await taskApi.create(taskData);
      addTask(task);

      toast.success(t('submit.toast.success'));
      router.push(`/tasks/${task.task_id}`);
    } catch (error: any) {
      toast.error(error.response?.data?.detail || t('submit.toast.failed'));
      console.error(error);
    } finally {
      setSubmitting(false);
      setLoading(false);
    }
  };

  const modeLabels: Record<AnalysisMode, string> = {
    promoters_pre: t('submit.mode.promoters_pre'),
    promoters: t('submit.mode.promoters'),
    intervals: t('submit.mode.intervals'),
  };

  return (
    <div className="max-w-5xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">{t('submit.title')}</h1>

      {/* Mode Selection — buttons say what the user provides; a short
          subtitle below the active button explains it in one line, and
          a collapsible details block expands the full when-to-pick. */}
      <div className="card mb-6">
        <h3 className="text-lg font-semibold mb-4">{t('submit.mode.heading')}</h3>
        <div className="flex flex-wrap gap-3">
          {(['promoters_pre', 'promoters', 'intervals'] as AnalysisMode[]).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`px-4 py-2 rounded-lg ${
                mode === m
                  ? 'bg-primary-700 text-white'
                  : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
              }`}
            >
              {modeLabels[m]}
            </button>
          ))}
        </div>
        <p className="mt-3 text-sm text-slate-600">
          {t(`submit.mode.${mode}.subtitle` as TranslationKey)}
        </p>
        <details className="mt-2 group">
          <summary className="cursor-pointer select-none text-xs font-medium text-slate-500 hover:text-slate-700">
            <span className="group-open:hidden">{t('submit.mode.show_details')}</span>
            <span className="hidden group-open:inline">{t('submit.mode.hide_details')}</span>
          </summary>
          <p className="mt-2 rounded-md border border-slate-200 bg-slate-50 p-3 text-sm leading-relaxed text-slate-700">
            {t(`submit.mode.${mode}.details` as TranslationKey)}
          </p>
        </details>
      </div>

      {/* Email */}
      <div className="card mb-6">
        <label className="label">{t('submit.email.label')}</label>
        <input
          type="email"
          className="input-field"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder={t('submit.email.placeholder')}
        />
        <p className="mt-1 text-sm text-slate-500">{t('submit.email.help')}</p>
      </div>

      {/* Pre-computed Selection */}
      {mode === 'promoters_pre' && (
        <div className="card mb-6">
          <h3 className="text-lg font-semibold mb-4">{t('submit.db.heading')}</h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label">{t('submit.db.species')}</label>
              <select
                className="select-field"
                value={selectedSpecies}
                onChange={(e) => {
                  setSelectedSpecies(e.target.value);
                  updateFiles({ premade_index: '' });
                }}
              >
                <option value="">{t('submit.db.species.placeholder')}</option>
                {speciesList.map((sp) => (
                  <option key={sp} value={sp}>{humanize(sp)}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">{t('submit.db.motif')}</label>
              <select
                className="select-field"
                value={files.premade_index}
                onChange={(e) => updateFiles({ premade_index: e.target.value })}
                disabled={!selectedSpecies}
              >
                <option value="">
                  {selectedSpecies ? t('submit.db.motif.placeholder') : t('submit.db.motif.placeholder_pick_species')}
                </option>
                {motifDbOptions.map((entry) => (
                  <option key={entry.value} value={entry.value}>
                    {humanize(entry.motif_db)}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {indexingEntries.length === 0 && (
            <p className="mt-2 text-sm text-slate-500">
              {t('submit.db.empty.before')}
              <code className="mx-1 px-1 bg-slate-100 rounded">make fetch-data</code>
              {t('submit.db.empty.after')} <code className="px-1 bg-slate-100 rounded">data/precomputed_indexes/</code>.
            </p>
          )}

          {/* Expandable detail panel — appears after a species is picked. */}
          {selectedSpecies && (
            <>
              <div
                className={`overflow-hidden transition-[max-height] duration-300 ease-out ${
                  detailOpen ? 'max-h-[1200px]' : 'max-h-0'
                }`}
              >
                <div className="mt-4 pt-4 border-t border-slate-200 grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Species block */}
                  <div className="bg-slate-50 border border-slate-200 rounded-lg p-4">
                    <h4 className="text-xs font-semibold tracking-wide text-slate-500 uppercase mb-2">
                      {t('submit.db.detail.species')}
                    </h4>
                    <div className="text-primary-700 font-medium mb-3">
                      {currentSpecies?.humanized ?? humanize(selectedSpecies)}
                    </div>
                    {currentSpecies?.description && (
                      <p className="text-sm text-slate-600 mb-3 leading-relaxed">
                        {currentSpecies.description}
                      </p>
                    )}
                    {currentSpecies?.genome_name && (
                      <div className="text-sm mb-1">
                        <span className="text-slate-500">{t('submit.db.detail.genome')} </span>
                        {currentSpecies.genome_link ? (
                          <a
                            href={currentSpecies.genome_link}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-primary-700 hover:underline break-all"
                          >
                            {currentSpecies.genome_name}
                          </a>
                        ) : (
                          <span className="text-slate-700">{currentSpecies.genome_name}</span>
                        )}
                      </div>
                    )}
                    {currentSpecies?.annotation_name && (
                      <div className="text-sm mb-3">
                        <span className="text-slate-500">{t('submit.db.detail.annotation')} </span>
                        {currentSpecies.annotation_link ? (
                          <a
                            href={currentSpecies.annotation_link}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-primary-700 hover:underline break-all"
                          >
                            {currentSpecies.annotation_name}
                          </a>
                        ) : (
                          <span className="text-slate-700">{currentSpecies.annotation_name}</span>
                        )}
                      </div>
                    )}
                    {currentSpecies && (
                      <div className="text-sm">
                        <div className="text-slate-500 mb-1">{t('submit.db.detail.genes')}</div>
                        <ul className="list-disc list-inside text-slate-700 mb-1 ml-1">
                          {currentSpecies.gene_sample.map((g) => (
                            <li key={g}>{g}</li>
                          ))}
                          {currentSpecies.gene_count > currentSpecies.gene_sample.length && (
                            <li className="list-none text-slate-400">…</li>
                          )}
                        </ul>
                        <div className="text-emerald-700 font-medium">
                          {t('submit.db.detail.total')} {currentSpecies.gene_count.toLocaleString()}
                        </div>
                      </div>
                    )}
                    {!currentSpecies && speciesLoading && (
                      <div className="text-sm text-slate-500">{t('submit.db.detail.loading')}</div>
                    )}
                  </div>

                  {/* Motif DB block */}
                  <div className="bg-slate-50 border border-slate-200 rounded-lg p-4">
                    <h4 className="text-xs font-semibold tracking-wide text-slate-500 uppercase mb-2">
                      {t('submit.db.detail.motif')}
                    </h4>
                    {!files.premade_index ? (
                      <p className="text-sm text-slate-500 italic">
                        {t('submit.db.detail.pick_motif')}
                      </p>
                    ) : (
                      <>
                        <div className="mb-3">
                          {currentMotifDb?.source_link ? (
                            <a
                              href={currentMotifDb.source_link}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-primary-700 font-medium hover:underline"
                            >
                              {currentMotifDb.humanized}
                            </a>
                          ) : (
                            <span className="text-primary-700 font-medium">
                              {currentMotifDb?.humanized ?? humanize(selectedEntry?.motif_db ?? '')}
                            </span>
                          )}
                        </div>
                        {currentMotifDb && (
                          <div className="text-sm">
                            <div className="text-slate-500 mb-1">{t('submit.db.detail.motifs')}</div>
                            <ul className="list-disc list-inside text-slate-700 mb-1 ml-1">
                              {currentMotifDb.motif_sample.map((m) => (
                                <li key={m}>{m}</li>
                              ))}
                              {currentMotifDb.motif_count > currentMotifDb.motif_sample.length && (
                                <li className="list-none text-slate-400">…</li>
                              )}
                            </ul>
                            <div className="text-emerald-700 font-medium">
                              {t('submit.db.detail.total')} {currentMotifDb.motif_count.toLocaleString()}
                            </div>
                          </div>
                        )}
                        {!currentMotifDb && motifDbLoading && (
                          <div className="text-sm text-slate-500">{t('submit.db.detail.loading')}</div>
                        )}
                      </>
                    )}
                  </div>
                </div>
              </div>

              <button
                type="button"
                onClick={() => setDetailOpen((v) => !v)}
                aria-expanded={detailOpen}
                className="mt-3 w-full flex items-center justify-center gap-2 py-2 border-t border-slate-200 text-sm text-primary-700 hover:text-primary-800 hover:bg-slate-50 transition-colors"
              >
                <span>{detailOpen ? t('submit.db.detail.hide') : t('submit.db.detail.show')}</span>
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className={`transition-transform duration-200 ${detailOpen ? 'rotate-180' : ''}`}
                >
                  <polyline points="6 9 12 15 18 9" />
                </svg>
              </button>
            </>
          )}
        </div>
      )}

      {/* File Uploads */}
      <div className="card mb-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold">{t('submit.upload.heading')}</h3>
          <span className="text-xs text-slate-500">
            {t('submit.upload.example_hint_pre')}{' '}
            <span className="font-medium text-primary-700">{t('submit.upload.example_hint_link')}</span>{' '}
            {t('submit.upload.example_hint_post')}
          </span>
        </div>

        {/* [&>*]:mb-0 cancels FileUpload's own bottom margin so grid gap stays uniform. */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 [&>*]:mb-0">
          {(mode === 'promoters' || mode === 'intervals') && (
            <FileUpload
              label={mode === 'intervals' ? t('submit.upload.label.intervals_fa') : t('submit.upload.label.genome')}
              accept=".fasta,.fa,.fasta.gz,.fa.gz"
              onUpload={(file, p) => handleFileUpload(file, 'fasta', p)}
              onClear={() => handleFileClear('fasta')}
              currentFile={files.fasta?.name}
              currentFileSize={files.fasta?.size}
              required
              demoUrl={`/api/demo/${mode}/fasta`}
              demoFilename={mode === 'intervals' ? 'intervals.fa' : 'TAIR10.fasta'}
              previewTitle={t('submit.preview.fasta_title')}
              previewNote={t('submit.preview.fasta_note')}
              previewContent={EXAMPLE_FASTA}
            />
          )}

          {mode === 'promoters' && (
            <FileUpload
              label={t('submit.upload.label.annotation')}
              accept=".gff3,.gff,.gff3.gz,.gff.gz"
              onUpload={(file, p) => handleFileUpload(file, 'gff3', p)}
              onClear={() => handleFileClear('gff3')}
              currentFile={files.gff3?.name}
              currentFileSize={files.gff3?.size}
              required
              demoUrl="/api/demo/promoters/gff3"
              demoFilename="TAIR10.gff3"
              previewTitle={t('submit.preview.gff3_title')}
              previewNote={t('submit.preview.gff3_note')}
              previewContent={EXAMPLE_GFF3}
            />
          )}

          {(mode === 'promoters' || mode === 'intervals') && (
            <FileUpload
              label={t('submit.upload.label.motif')}
              accept=".meme"
              onUpload={(file, p) => handleFileUpload(file, 'meme', p)}
              onClear={() => handleFileClear('meme')}
              currentFile={files.meme?.name}
              currentFileSize={files.meme?.size}
              required
              demoUrl={`/api/demo/${mode}/meme`}
              demoFilename={mode === 'intervals' ? 'motif.meme' : 'Franco-Zorrilla_et_al_2014.meme'}
              previewTitle={t('submit.preview.meme_title')}
              previewNote={t('submit.preview.meme_note')}
              previewContent={EXAMPLE_MEME}
            />
          )}

          <div className={mode === 'promoters_pre' ? 'md:col-span-2' : ''}>
            <FileUpload
              label={mode === 'intervals' ? t('submit.upload.label.peaks') : t('submit.upload.label.gene_list')}
              accept=".txt,.tsv"
              onUpload={(file, p) => handleFileUpload(file, 'genes', p)}
              onClear={() => handleFileClear('genes')}
              currentFile={files.genes?.name}
              currentFileSize={files.genes?.size}
              helpText={t('submit.upload.help.gene_list')}
              required
              demoUrl={`/api/demo/${mode}/genes`}
              demoFilename={mode === 'intervals' ? 'peaks.txt' : 'genes_cell_type_treatment.txt'}
              previewTitle={t(mode === 'intervals' ? 'submit.preview.peaks_title' : 'submit.preview.gene_list_title')}
              previewNote={t(mode === 'intervals' ? 'submit.preview.peaks_note' : 'submit.preview.gene_list_note')}
              previewContent={mode === 'intervals' ? EXAMPLE_PEAK_LIST : EXAMPLE_GENE_LIST}
            />
          </div>
        </div>
      </div>

      {/* Parameters */}
      <ParameterPanel
        mode={mode}
        params={params}
        onChange={handleParamChange}
        fixedParams={indexingEntries.find((e) => e.value === files.premade_index)?.fixed_params}
      />

      {/* Submit + estimate */}
      <div className="mt-6 flex flex-col items-end gap-2">
        {(estimate || estimateLoading) && (
          <div className="text-sm text-slate-600">
            {estimateLoading && !estimate ? (
              <span className="text-slate-400">{t('submit.estimate.loading')}</span>
            ) : estimate ? (
              <>
                <span className="text-slate-500">{t('submit.estimate.label')}: </span>
                <span className="font-medium text-slate-900">
                  {formatRuntimeRange(estimate.lower_seconds, estimate.upper_seconds, t)}
                </span>
                <span className="ml-2 text-xs text-slate-400">
                  {t('submit.estimate.note')}
                </span>
              </>
            ) : null}
          </div>
        )}
        <button
          onClick={handleSubmit}
          disabled={submitting}
          className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {submitting ? t('submit.button.submitting') : t('submit.button.submit')}
        </button>
      </div>
    </div>
  );
}

function SubmitFallback() {
  const { t } = useTranslation();
  return <div className="text-center py-12">{t('submit.suspense.loading')}</div>;
}

export default function SubmitPage() {
  return (
    <Suspense fallback={<SubmitFallback />}>
      <SubmitPageContent />
    </Suspense>
  );
}
