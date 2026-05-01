'use client';

import { TaskResponse } from '@/lib/types';
import TaskStatusBadge from './TaskStatusBadge';
import { taskApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';
import { TranslationKey } from '@/lib/translations';
import { formatBytes } from '@/lib/runtime';

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

  return (
    <div className="card hover:shadow-md transition-shadow cursor-pointer" onClick={onSelect}>
      <div className="flex justify-between items-start mb-3">
        <div>
          <h3 className="font-medium text-slate-900">{task.task_id}</h3>
          <p className="text-sm text-slate-500">{t(MODE_KEYS[task.mode])}</p>
        </div>
        <TaskStatusBadge status={task.status} />
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

      {task.status === 'completed' && task.result_link && (
        <div className="mt-4">
          <a
            href={taskApi.downloadResult(task.task_id)}
            className="btn-primary inline-block text-sm"
            onClick={(e) => e.stopPropagation()}
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

      {task.status === 'failed' && task.error_message && (
        <div className="mt-4 p-3 bg-red-50 rounded-lg text-sm text-red-700">
          {task.error_message}
        </div>
      )}
    </div>
  );
}
