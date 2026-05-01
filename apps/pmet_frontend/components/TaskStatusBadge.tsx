'use client';

import { useTranslation } from '@/lib/i18n';
import { TranslationKey } from '@/lib/translations';

// The persisted status enum (TaskStatus) plus two synthesised UI-only
// values that the backend's derive_effective_status() can return:
//   - `completed_with_warnings`: ran clean but a stage was skipped with
//     a note (currently only the "rendering had warnings" path).
//   - `partial_success`: persisted=failed BUT pairing produced
//     motif_output.txt — late-stage crash didn't lose the data, so a
//     hard red "Failed" badge would be misleading.
type ExtendedStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'completed_with_warnings'
  | 'partial_success'
  | 'failed'
  | 'cancelled';

interface TaskStatusBadgeProps {
  status: ExtendedStatus | string;
}

const statusConfig: Record<ExtendedStatus, { labelKey: TranslationKey; className: string }> = {
  pending:                 { labelKey: 'status.pending',                 className: 'bg-yellow-100 text-yellow-800' },
  running:                 { labelKey: 'status.running',                 className: 'bg-blue-100 text-blue-800' },
  completed:               { labelKey: 'status.completed',               className: 'bg-green-100 text-green-800' },
  completed_with_warnings: { labelKey: 'status.completed_with_warnings', className: 'bg-emerald-100 text-emerald-800 ring-1 ring-amber-300' },
  partial_success:         { labelKey: 'status.partial_success',         className: 'bg-amber-100 text-amber-800' },
  failed:                  { labelKey: 'status.failed',                  className: 'bg-red-100 text-red-800' },
  cancelled:               { labelKey: 'status.cancelled',               className: 'bg-slate-200 text-slate-700' },
};

const fallback = statusConfig.pending;

export default function TaskStatusBadge({ status }: TaskStatusBadgeProps) {
  const { t } = useTranslation();
  const config = (statusConfig as Record<string, typeof fallback>)[status] ?? fallback;
  return (
    <span className={`px-2 py-1 rounded-full text-sm font-medium ${config.className}`}>
      {t(config.labelKey)}
    </span>
  );
}
