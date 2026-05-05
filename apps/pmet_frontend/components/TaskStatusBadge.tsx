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

// Hairline-on-soft-fill chips, mirroring the SVG card vocabulary
// (single 1px stroke + low-saturation interior fill). Saturated brand
// 100s are kept only for "alarm" semantics (failed / partial).
const statusConfig: Record<ExtendedStatus, { labelKey: TranslationKey; className: string; dot: string }> = {
  pending:                 { labelKey: 'status.pending',                 className: 'bg-amber-50 text-amber-800 border-amber-200',           dot: 'bg-amber-500' },
  running:                 { labelKey: 'status.running',                 className: 'bg-sky-50 text-sky-800 border-sky-200',                 dot: 'bg-sky-500' },
  completed:               { labelKey: 'status.completed',               className: 'bg-primary-50 text-primary-800 border-primary-100',    dot: 'bg-primary-700' },
  completed_with_warnings: { labelKey: 'status.completed_with_warnings', className: 'bg-primary-50 text-primary-800 border-amber-300',      dot: 'bg-amber-500' },
  partial_success:         { labelKey: 'status.partial_success',         className: 'bg-amber-50 text-amber-800 border-amber-200',          dot: 'bg-amber-500' },
  failed:                  { labelKey: 'status.failed',                  className: 'bg-red-50 text-red-800 border-red-200',                dot: 'bg-red-500' },
  cancelled:               { labelKey: 'status.cancelled',               className: 'bg-slate-50 text-slate-700 border-hairline',           dot: 'bg-slate-400' },
};

const fallback = statusConfig.pending;

export default function TaskStatusBadge({ status }: TaskStatusBadgeProps) {
  const { t } = useTranslation();
  const config = (statusConfig as Record<string, typeof fallback>)[status] ?? fallback;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${config.className}`}>
      <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${config.dot}`} />
      {t(config.labelKey)}
    </span>
  );
}
