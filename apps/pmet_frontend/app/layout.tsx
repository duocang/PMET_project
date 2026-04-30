import './globals.css';
import type { Metadata } from 'next';
import { Toaster } from 'react-hot-toast';
import { I18nProvider } from '@/lib/i18n';
import { NavBar } from '@/components/NavBar';
import { SiteFooter } from '@/components/SiteFooter';

export const metadata: Metadata = {
  title: 'PMET - Paired Motif Enrichment Tool',
  description:
    'Identify cooperative transcription factor activity by evaluating motif combinations across promoter sets',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="scroll-smooth">
      <body className="flex min-h-screen flex-col">
        <Toaster position="bottom-right" />
        <I18nProvider>
          <NavBar />
          <main className="page-shell flex-1 py-8">{children}</main>
          <SiteFooter />
        </I18nProvider>
      </body>
    </html>
  );
}
