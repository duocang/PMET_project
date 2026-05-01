'use client';

import { Fragment } from 'react';
import { TaskResponse } from '@/lib/types';
import TaskStatusBadge from './TaskStatusBadge';
import StageBadge from './StageBadge';
import { taskApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';
import { TranslationKey } from '@/lib/translations';
import { formatBytes, summarizeError } from '@/lib/runtime';

interface TaskCardProps {
  task: TaskResponse;
  onSelect?: () => void;
}

const MODE_KEYS: Record<string, TranslationKey> = {
  promoters_pre: 'mode.promoters_pre',
  promoters: 'mode.promoters',
  intervals: 'mode.intervals',
};

export default function TaskCard({ task, onSelect }: TaskCardProps) {
  const { t } = useTranslation();

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleString();
  };

  // Effective status drives the badge and the choice between primary
  // banners — the persisted `task.status` may say "failed" while the FS
  // shows partial_success / completed_with_warnings, and we want both
  // list and detail views to render that distinction the same way.
  const displayStatus = task.effective_status ?? task.status;

  // Disclosure (stages timeline + warnings + full error) is only worth
  // surfacing when there's actually something to show. Skip it on
  // pristine completed / pending tasks where the badge alone is enough.
  const hasStageDetail = (task.stages && task.stages.length > 0) ||
    (task.warnings && task.warnings.length > 0) ||
    !!task.error_message;

  const stopPropagation = (e: React.MouseEvent | React.SyntheticEvent) =>
    e.stopPropagation();

  return (
    <div className="card hover:shadow-md transition-shadow cursor-pointer" onClick={onSelect}>
      <div className="flex justify-between items-start mb-3">
        <div>
          <h3 className="font-medium text-slate-900">{task.task_id}</h3>
          <p className="text-sm text-slate-500">{t(MODE_KEYS[task.mode])}</p>
        </div>
        <TaskStatusBadge status={displayStatus} />
      </div>

      <div className="grid grid-cols-2 gap-4 text-sm">
        <div>
          <span className="text-slate-500">{t('taskcard.email')}</span>
          <span className="ml-2">{task.email}</span>
        </div>
        <div>
          <span className="text-slate-500">{t('taskcard.created')}</span>
          <span className="ml-2">{formatDate(task.created_at)}</span>
        </div>
      </div>

      {/* Primary action: success download (compact) */}
      {task.status === 'completed' && task.result_link && (
        <div className="mt-4">
          <a
            href={taskApi.downloadResult(task.task_id)}
            className="btn-primary inline-block text-sm"
            onClick={stopPropagation}
          >
            {t('taskcard.download')}
            {task.result_size_bytes != null && (
              <span className="ml-1 font-normal opacity-80">
                ({formatBytes(task.result_size_bytes)})
              </span>
            )}
          </a>
        </div>
      )}

      {/* Primary action: partial-result rescue when pairing succeeded but
          a late stage crashed. Replaces the raw error block — the user
          gets the actionable thing (the file) up front, and the error
          itself moves into the disclosure below. */}
      {task.partial_result_link && (
        <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 px-3 py-2">
          <p className="text-xs font-semibold text-amber-800">
            {t('task.partial_available')}
          </p>
          <a
            href={task.partial_result_link}
            download={`${task.task_id}_motif_output.txt`}
            className="mt-1 inline-block text-sm font-semibold text-amber-800 underline hover:text-amber-900"
            onClick={stopPropagation}
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

      {/* Collapsible: stages timeline + warnings + full error. Hidden by
          default so the card stays compact on long lists; expands in
          place when the user wants the full picture without leaving the
          list view. */}
      {hasStageDetail && (
        <details
          className="mt-3 group"
          onClick={stopPropagation}
        >
          <summary className="cursor-pointer select-none text-xs font-medium text-slate-500 hover:text-slate-700">
            <span className="group-open:hidden">{t('taskcard.show_details')}</span>
            <span className="hidden group-open:inline">{t('taskcard.hide_details')}</span>
          </summary>
          <div className="mt-2 space-y-3">
            {task.stages && task.stages.length > 0 && (
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
            )}
            {task.warnings && task.warnings.length > 0 && (
              <ul className="space-y-1 text-xs text-amber-700">
                {task.warnings.map((w) => (
                  <li key={w}>• {w}</li>
                ))}
              </ul>
            )}
            {task.error_message && (
              <details className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs">
                <summary className="cursor-pointer select-none font-medium text-slate-600 hover:text-slate-800">
                  <span className="text-red-600">⚠</span>{' '}
                  <span className="text-slate-700">
                    {summarizeError(task.error_message)}
                  </span>
                </summary>
                <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-all rounded bg-white p-2 font-mono text-xs leading-snug text-slate-600">
                  {task.error_message}
                </pre>
              </details>
            )}
          </div>
        </details>
      )}
    </div>
  );
}
