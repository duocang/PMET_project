'use client';

import type { TaskStage } from '@/lib/types';
import type { TranslationKey } from '@/lib/translations';

// Visual treatment for each FS-derived stage state. Kept in one place so
// the detail page and the list-card collapsible render the same chips.
//   amber = something went wrong but wasn't fatal (heatmap render, zip)
//   slate (precomputed) = by-design absence so the user doesn't read it
//   as a problem (e.g. promoters_pre uses a precomputed index).
export const STAGE_STYLES: Record<
  TaskStage['state'],
  { icon: string; cls: string }
> = {
  pending:     { icon: '○', cls: 'bg-slate-50 text-slate-500 border-hairline' },
  running:     { icon: '◔', cls: 'bg-sky-50 text-sky-700 border-sky-200' },
  completed:   { icon: '✓', cls: 'bg-primary-50 text-primary-800 border-primary-100' },
  failed:      { icon: '✕', cls: 'bg-red-50 text-red-700 border-red-200' },
  skipped:     { icon: '⊘', cls: 'bg-amber-50 text-amber-700 border-amber-200' },
  precomputed: { icon: '↻', cls: 'bg-slate-50 text-slate-600 border-hairline' },
};

interface StageBadgeProps {
  stage: TaskStage;
  t: (k: TranslationKey) => string;
}

export default function StageBadge({ stage, t }: StageBadgeProps) {
  const style = STAGE_STYLES[stage.state];
  const labelKey = `task.stages.${stage.name}` as TranslationKey;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium ${style.cls}`}
      title={stage.note ?? undefined}
    >
      <span aria-hidden className="text-sm leading-none">{style.icon}</span>
      <span>{t(labelKey)}</span>
    </span>
  );
}
