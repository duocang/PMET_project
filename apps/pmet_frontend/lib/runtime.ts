import { TranslationKey } from './translations';

type Translate = (key: TranslationKey) => string;

export function formatRuntimeRange(loSec: number, hiSec: number, t: Translate): string {
  const sep = ` ${t('submit.estimate.range_sep')} `;
  if (hiSec < 90) {
    return `${Math.max(1, Math.round(loSec))}${sep}${Math.max(1, Math.round(hiSec))} ${t('submit.estimate.unit.seconds')}`;
  }
  if (hiSec < 60 * 90) {
    return `${Math.max(1, Math.round(loSec / 60))}${sep}${Math.max(1, Math.round(hiSec / 60))} ${t('submit.estimate.unit.minutes')}`;
  }
  const hLo = (loSec / 3600).toFixed(1).replace(/\.0$/, '');
  const hHi = (hiSec / 3600).toFixed(1).replace(/\.0$/, '');
  return `${hLo}${sep}${hHi} ${t('submit.estimate.unit.hours')}`;
}

export function humanizeIdentifier(value?: string | null): string {
  return (value || '').replace(/_/g, ' ');
}

// Pull a single user-facing line out of a verbose worker error_message.
// PMET errors typically bury the actually informative line under hundreds
// of lines of R warnings; surface that informative line in the collapsed
// summary so the user gets the gist without unfolding the full traceback.
export function summarizeError(msg: string): string {
  const lines = msg
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean);
  const err =
    lines.find((l) => /^error\b/i.test(l)) ||
    lines.find((l) => l.startsWith('!')) ||
    lines.find((l) => /^command failed/i.test(l));
  const pick = err ?? lines[0] ?? '';
  return pick.length > 140 ? pick.slice(0, 137) + '…' : pick;
}

// Used by the partial-result banner so users see "(~993 MB)" before they
// click into a multi-GB stream. Binary-prefix (KiB/MiB/GiB) is the more
// honest choice for raw byte counts, but ordinary users read MB and GB —
// stick with the SI labels they recognize while dividing by 1024 (the
// off-by-2.4% gap doesn't matter for "is this download going to hurt").
export function formatBytes(bytes?: number | null): string {
  if (bytes == null || !Number.isFinite(bytes) || bytes < 0) return '';
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb < 10 ? kb.toFixed(1) : Math.round(kb)} KB`;
  const mb = kb / 1024;
  if (mb < 1024) return `${mb < 10 ? mb.toFixed(1) : Math.round(mb)} MB`;
  const gb = mb / 1024;
  return `${gb < 10 ? gb.toFixed(2) : gb.toFixed(1)} GB`;
}
