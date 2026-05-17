import './globals.css';
import type { Metadata, Viewport } from 'next';
import { Toaster } from 'react-hot-toast';
import { I18nProvider } from '@/lib/i18n';
import { HtmlLangSync } from '@/components/HtmlLangSync';
import { NavBar } from '@/components/NavBar';
import { SiteFooter } from '@/components/SiteFooter';
import { SkipLink } from '@/components/SkipLink';

export const metadata: Metadata = {
  title: 'PMET - Paired Motif Enrichment Tool',
  description:
    'Identify cooperative transcription factor activity by evaluating motif combinations across promoter sets',
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#f4f7f8' },
    { media: '(prefers-color-scheme: dark)', color: '#f4f7f8' },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="scroll-smooth">
      <body className="flex min-h-screen flex-col">
        <Toaster position="bottom-right" />
        <I18nProvider>
          <HtmlLangSync />
          <SkipLink />
          <NavBar />
          <main id="main-content" tabIndex={-1} className="page-shell flex-1 py-8 focus:outline-none">
            {children}
          </main>
          <SiteFooter />
        </I18nProvider>
      </body>
    </html>
  );
}
