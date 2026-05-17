'use client';

import { useTranslation } from '@/lib/i18n';

export function SkipLink() {
  const { t } = useTranslation();
  return (
    <a href="#main-content" className="skip-link">
      {t('a11y.skipToContent')}
    </a>
  );
}
