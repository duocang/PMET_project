'use client';

import { useState, useEffect, Fragment } from 'react';
import { taskApi } from '@/lib/api';
import { TaskResponse, TaskProgress } from '@/lib/types';
import TaskStatusBadge from '@/components/TaskStatusBadge';
import Link from 'next/link';
import { useTranslation } from '@/lib/i18n';
import { TranslationKey } from '@/lib/translations';
import { formatBytes, formatRuntimeRange, humanizeIdentifier, summarizeError } from '@/lib/runtime';
import StageBadge from '@/components/StageBadge';

interface PageProps {
  params: { id: string };
}

const MODE_KEYS: Record<string, TranslationKey> = {
  promoters_pre: 'mode.promoters_pre',
  promoters: 'mode.promoters',
  intervals: 'mode.intervals',
};

export default function TaskDetailPage({ params }: PageProps) {
  const { id } = params;
  const { t } = useTranslation();
  const [task, setTask] = useState<TaskResponse | null>(null);
  const [progress, setProgress] = useState<TaskProgress | null>(null);
  const [loading, setLoading] = useState(true);
  const [polling, setPolling] = useState(false);

  useEffect(() => {
    fetchTask();
    return () => setPolling(false);
  }, [id]);

  useEffect(() => {
    if (task && (task.status === 'pending' || task.status === 'running')) {
      setPolling(true);
      const tick = () => {
        fetchTask();
        // Pull live stage from the worker's progress.json. Best-effort: 404
        // / parse failure just leaves the previous bar in place.
        taskApi.progress(id).then(setProgress).catch(() => {});
      };
      tick();
      const interval = setInterval(tick, 5000);
      return () => {
        clearInterval(interval);
        setPolling(false);
      };
    } else {
      setProgress(null);
    }
  }, [task?.status, id]);

  const fetchTask = async () => {
    try {
      const response = await taskApi.get(id);
      setTask(response);
    } catch (error) {
      console.error('Failed to fetch task:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="max-w-5xl mx-auto text-center py-12 text-slate-500">
        {t('task.loading')}
      </div>
    );
  }

  if (!task) {
    return (
      <div className="max-w-5xl mx-auto text-center py-12">
        <p className="text-slate-500">{t('task.not_found')}</p>
        <Link href="/tasks" className="text-primary-700 hover:underline mt-4 inline-block">
          {t('task.back')}
        </Link>
      </div>
    );
  }

  const precomputedInfo = getPrecomputedIndexInfo(task);

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <Link href="/tasks" className="text-sm text-slate-500 hover:text-slate-700">
        {t('task.back')}
      </Link>

      {/* Header card: ID + mode + status + action buttons */}
      <div className="card">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div className="min-w-0">
            <h1 className="break-all font-mono text-xl font-semibold text-slate-950 md:text-2xl">
              {task.task_id}
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              {t(MODE_KEYS[task.mode])} · {task.email}
            </p>
          </div>
          <TaskStatusBadge status={task.effective_status ?? task.status} />
        </div>

        {task.stages && task.stages.length > 0 && (
          <div className="mt-5">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
              {t('task.stages.heading')}
            </h3>
            <div className="flex flex-wrap items-center gap-2">
              {task.stages.map((stage, idx) => (
                <Fragment key={stage.name}>
                  <StageBadge stage={stage} t={t} />
                  {idx < task.stages!.length - 1 && (
                    <span aria-hidden className="text-slate-300">→</span>
                  )}
                </Fragment>
              ))}
            </div>
            {task.warnings && task.warnings.length > 0 && (
              <ul className="mt-3 space-y-1 text-xs text-amber-700">
                {task.warnings.map((w) => (
                  <li key={w}>• {w}</li>
                ))}
              </ul>
            )}
          </div>
        )}

        {polling && (
          <div className="mt-5 rounded-md bg-blue-50 px-4 py-3 text-sm text-blue-700">
            <div className="flex items-center gap-2">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
              <span className="font-medium">
                {progress?.label ?? t('task.running_msg')}
              </span>
              {progress?.stage_index && progress?.total_stages ? (
                <span className="text-blue-500">
                  · {progress.stage_index} / {progress.total_stages}
                </span>
              ) : null}
            </div>
            {progress?.stage_index && progress?.total_stages && (
              <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-blue-100">
                <div
                  className="h-full bg-blue-500 transition-all duration-500 ease-out"
                  style={{
                    width: `${activeStagePercent(progress.stage_index, progress.total_stages)}%`,
                  }}
                />
              </div>
            )}
          </div>
        )}

        {task.partial_result_link && (
          <div className="mt-5 rounded-md border border-amber-200 bg-amber-50 px-4 py-3">
            <h3 className="mb-1 text-sm font-semibold text-amber-800">
              {t('task.partial_available')}
            </h3>
            <p className="mb-2 text-sm text-amber-700">
              {t('task.download_partial_help')}
            </p>
            <a
              href={task.partial_result_link}
              download={`${task.task_id}_motif_output.txt`}
              className="text-sm font-semibold text-amber-800 underline hover:text-amber-900"
            >
              {t('task.download_partial')}
              {task.partial_result_size_bytes != null && (
                <span className="ml-1 font-normal text-amber-700">
                  ({formatBytes(task.partial_result_size_bytes)})
                </span>
              )}
            </a>
          </div>
        )}

        {task.error_message && (
          <details className="mt-4 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs">
            <summary className="cursor-pointer select-none font-medium text-slate-600 hover:text-slate-800">
              <span className="text-red-600">⚠</span>{' '}
              <span className="text-slate-700">
                {summarizeError(task.error_message)}
              </span>
              <span className="ml-2 text-slate-400">
                · {t('task.error.show_details')}
              </span>
            </summary>
            <pre className="mt-2 max-h-60 overflow-auto whitespace-pre-wrap break-all rounded bg-white p-2 font-mono text-xs leading-snug text-slate-600">
              {task.error_message}
            </pre>
          </details>
        )}

        {task.status === 'completed' && (
          <div className="mt-5 flex flex-wrap gap-3">
            <a href={taskApi.downloadResult(task.task_id)} className="btn-primary">
              {t('task.download')}
              {task.result_size_bytes != null && (
                <span className="ml-1 font-normal opacity-80">
                  ({formatBytes(task.result_size_bytes)})
                </span>
              )}
            </a>
            <Link href={`/tasks/${task.task_id}/visualize`} className="btn-secondary">
              {t('task.visualize')}
            </Link>
          </div>
        )}
      </div>

      {/* Analysis, timeline + parameters */}
      <div className="grid gap-6 md:grid-cols-2">
        <Card title={t('task.section.analysis')}>
          <DataRow label={t('task.analysis.mode')} value={t(MODE_KEYS[task.mode])} />
          {task.runtime_estimate && (
            <DataRow
              label={t('task.analysis.estimated_runtime')}
              value={formatRuntimeRange(
                task.runtime_estimate.lower_seconds,
                task.runtime_estimate.upper_seconds,
                t,
              )}
            />
          )}
          {task.mode === 'promoters_pre' && precomputedInfo.species && (
            <DataRow
              label={t('task.analysis.species')}
              value={humanizeIdentifier(precomputedInfo.species)}
            />
          )}
          {task.mode === 'promoters_pre' && precomputedInfo.motifDb && (
            <DataRow
              label={t('task.analysis.motif_db')}
              value={humanizeIdentifier(precomputedInfo.motifDb)}
            />
          )}
        </Card>

        <Card title={t('task.section.timeline')}>
          <DataRow label={t('task.created')} value={formatDate(task.created_at)} />
          {task.started_at && (
            <DataRow label={t('task.started')} value={formatDate(task.started_at)} />
          )}
          {task.completed_at && (
            <DataRow label={t('task.completed')} value={formatDate(task.completed_at)} />
          )}
          {task.started_at && task.completed_at && (
            <DataRow
              label={t('task.duration')}
              value={formatDuration(task.started_at, task.completed_at)}
            />
          )}
        </Card>

        <Card title={t('task.section.params')}>
          {task.promoter_length != null && (
            <DataRow
              label={t('task.param.promoter_length')}
              value={`${task.promoter_length} bp`}
            />
          )}
          {task.max_match != null && (
            <DataRow label={t('task.param.max_match')} value={String(task.max_match)} />
          )}
          {task.promoter_num != null && (
            <DataRow label={t('task.param.promoter_num')} value={String(task.promoter_num)} />
          )}
          {task.fimo_threshold != null && (
            <DataRow label={t('task.param.fimo_threshold')} value={String(task.fimo_threshold)} />
          )}
          {task.ic_threshold != null && (
            <DataRow label={t('task.param.ic_threshold')} value={String(task.ic_threshold)} />
          )}
          {task.utr5 && <DataRow label={t('task.param.utr5')} value={task.utr5} />}
          {task.promoters_overlap && (
            <DataRow label={t('task.param.overlap')} value={task.promoters_overlap} />
          )}
          {task.ncpu != null && (
            <DataRow label={t('task.param.threads')} value={String(task.ncpu)} />
          )}
        </Card>
      </div>

      {/* Input files */}
      {hasInputFiles(task) && (
        <Card title={t('task.section.inputs')}>
          {task.genes_file && (
            <FileRow label={t('task.file.genes')} path={task.genes_file} />
          )}
          {task.fasta_file && (
            <FileRow label={t('task.file.fasta')} path={task.fasta_file} />
          )}
          {task.gff3_file && (
            <FileRow label={t('task.file.gff3')} path={task.gff3_file} />
          )}
          {task.meme_file && <FileRow label={t('task.file.meme')} path={task.meme_file} />}
          {task.premade_index && (
            <FileRow label={t('task.file.premade')} path={task.premade_index} />
          )}
        </Card>
      )}
    </div>
  );
}

// ---------- helpers ----------

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="card">
      <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-slate-500">
        {title}
      </h2>
      <dl className="space-y-2.5">{children}</dl>
    </div>
  );
}

function DataRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5 sm:flex-row sm:items-baseline sm:justify-between sm:gap-4">
      <dt className="text-sm text-slate-500">{label}</dt>
      <dd className="text-sm font-medium text-slate-900">{value}</dd>
    </div>
  );
}

function FileRow({ label, path }: { label: string; path: string }) {
  // Show only the basename in the prominent slot; full path is shown small
  // below for debugging — useful when two uploads have the same filename.
  const basename = path.split('/').pop() ?? path;
  return (
    <div className="flex flex-col gap-0.5 sm:flex-row sm:items-baseline sm:justify-between sm:gap-4">
      <dt className="text-sm text-slate-500">{label}</dt>
      <dd className="min-w-0 sm:text-right">
        <div className="break-all font-mono text-sm text-slate-900">{basename}</div>
        <div className="break-all text-xs text-slate-400">{path}</div>
      </dd>
    </div>
  );
}

function hasInputFiles(t: TaskResponse) {
  return Boolean(
    t.genes_file || t.fasta_file || t.gff3_file || t.meme_file || t.premade_index,
  );
}

function activeStagePercent(stageIndex: number, totalStages: number) {
  if (totalStages <= 0) return 0;
  // Progress JSON is emitted at the start of each stage. Showing stage N/N as
  // 100% would imply the job is done while the final stage is still running,
  // so display the midpoint of the active stage and reserve 100% for terminal
  // completion.
  return Math.min(95, Math.max(5, ((stageIndex - 0.5) / totalStages) * 100));
}

function getPrecomputedIndexInfo(t: TaskResponse) {
  if (t.indexing_species || t.indexing_motif_db) {
    return { species: t.indexing_species || '', motifDb: t.indexing_motif_db || '' };
  }

  const parts = t.premade_index?.split('/') ?? [];
  const idx = parts.indexOf('precomputed_indexes');
  if (idx < 0 || parts.length <= idx + 2) {
    return { species: '', motifDb: '' };
  }
  return { species: parts[idx + 1], motifDb: parts[idx + 2] };
}

function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleString();
}

function formatDuration(startStr: string, endStr: string) {
  const ms = new Date(endStr).getTime() - new Date(startStr).getTime();
  if (ms < 0) return '—';
  const sec = Math.floor(ms / 1000);
  if (sec < 60) return `${sec}s`;
  const min = Math.floor(sec / 60);
  const remSec = sec % 60;
  if (min < 60) return `${min}m ${remSec}s`;
  const hr = Math.floor(min / 60);
  return `${hr}h ${min % 60}m`;
}

