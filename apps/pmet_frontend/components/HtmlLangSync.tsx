'use client';

import { useEffect } from 'react';
import { useTranslation } from '@/lib/i18n';

export function HtmlLangSync() {
  const { locale } = useTranslation();
  useEffect(() => {
    document.documentElement.lang = locale === 'zh' ? 'zh-Hans' : 'en';
  }, [locale]);
  return null;
}
