'use client';

import { TaskStatus } from '@/lib/types';
import { useTranslation } from '@/lib/i18n';
import { TranslationKey } from '@/lib/translations';

interface TaskStatusBadgeProps {
  status: TaskStatus;
}

const statusConfig: Record<TaskStatus, { labelKey: TranslationKey; className: string }> = {
  pending: { labelKey: 'status.pending', className: 'bg-yellow-100 text-yellow-800' },
  running: { labelKey: 'status.running', className: 'bg-blue-100 text-blue-800' },
  completed: { labelKey: 'status.completed', className: 'bg-green-100 text-green-800' },
  failed: { labelKey: 'status.failed', className: 'bg-red-100 text-red-800' },
  cancelled: { labelKey: 'status.cancelled', className: 'bg-slate-200 text-slate-700' },
};

export default function TaskStatusBadge({ status }: TaskStatusBadgeProps) {
  const { t } = useTranslation();
  const config = statusConfig[status];
  return (
    <span className={`px-2 py-1 rounded-full text-sm font-medium ${config.className}`}>
      {t(config.labelKey)}
    </span>
  );
}
