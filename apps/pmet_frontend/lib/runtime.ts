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
