'use client';

// Impressum (§ 5 TMG / § 18 MStV) — legal disclosure required for any
// publicly-reachable site operated from Germany. The German text is the
// legally binding version. English + 汉文 translations below are
// informational, switched by the user's current locale toggle.

import { useTranslation } from '@/lib/i18n';

export default function ImpressumPage() {
  const { locale } = useTranslation();

  return (
    <article className="prose prose-slate mx-auto max-w-3xl py-8">
      {/* German — always shown, legally binding */}
      <section>
        <h1>Impressum</h1>
        <p className="text-sm text-slate-500">
          Angaben gemäß § 5 TMG und § 18 MStV. Verbindliche Fassung in deutscher Sprache.
        </p>

        <h2>Anbieter</h2>
        <p>
          Wang Xuesong (王雪松)<br />
          Lynarstraße 26<br />
          13353 Berlin<br />
          Deutschland
        </p>

        <h2>Kontakt</h2>
        <p>
          E-Mail: <a href="mailto:questions@pmet.online">questions@pmet.online</a>
        </p>

        <h2>Inhaltlich verantwortlich gemäß § 18 Abs. 2 MStV</h2>
        <p>Wang Xuesong (王雪松), Anschrift wie oben.</p>

        <h2>Online-Streitbeilegung</h2>
        <p>
          Die Europäische Kommission stellt eine Plattform zur Online-Streitbeilegung (OS)
          bereit:{' '}
          <a href="https://ec.europa.eu/consumers/odr" target="_blank" rel="noopener noreferrer">
            https://ec.europa.eu/consumers/odr
          </a>
          . Unsere E-Mail-Adresse finden Sie oben. Wir sind nicht verpflichtet und nicht
          bereit, an einem Streitbeilegungsverfahren vor einer Verbraucherschlichtungsstelle
          teilzunehmen.
        </p>

        <h2>Haftungshinweis</h2>
        <p>
          PMET ist ein wissenschaftliches Werkzeug zur Motiv-Anreicherungsanalyse. Es liefert
          keine medizinischen, diagnostischen oder klinischen Aussagen. Trotz sorgfältiger
          inhaltlicher Kontrolle übernehmen wir keine Haftung für die Inhalte externer
          Links. Für den Inhalt der verlinkten Seiten sind ausschließlich deren Betreiber
          verantwortlich.
        </p>
      </section>

      <hr className="my-10" />

      {locale === 'en' && (
        <section>
          <h2 className="text-base font-semibold uppercase tracking-wider text-slate-500">
            English translation (informational)
          </h2>
          <h3>Provider</h3>
          <p>
            Wang Xuesong (王雪松)<br />
            Lynarstraße 26<br />
            13353 Berlin<br />
            Germany
          </p>
          <h3>Contact</h3>
          <p>
            E-mail: <a href="mailto:questions@pmet.online">questions@pmet.online</a>
          </p>
          <h3>Responsible for content under § 18(2) MStV</h3>
          <p>Wang Xuesong (王雪松), address as above.</p>
          <h3>Online dispute resolution</h3>
          <p>
            The European Commission provides a platform for online dispute resolution (ODR)
            at{' '}
            <a href="https://ec.europa.eu/consumers/odr" target="_blank" rel="noopener noreferrer">
              https://ec.europa.eu/consumers/odr
            </a>
            . We are not obliged and not willing to participate in dispute resolution
            proceedings before a consumer arbitration body.
          </p>
          <h3>Liability notice</h3>
          <p>
            PMET is a scientific tool for paired motif enrichment analysis. It provides no
            medical, diagnostic, or clinical advice. Despite careful curation we accept no
            liability for the contents of external links; the operators of the linked pages
            are solely responsible.
          </p>
        </section>
      )}

      {locale === 'zh' && (
        <section>
          <h2 className="text-base font-semibold uppercase tracking-wider text-slate-500">
            汉文翻译（仅供参考）
          </h2>
          <h3>运营者</h3>
          <p>
            王雪松 (Wang Xuesong)<br />
            Lynarstraße 26<br />
            13353 柏林<br />
            德国
          </p>
          <h3>联系方式</h3>
          <p>
            电子邮件：<a href="mailto:questions@pmet.online">questions@pmet.online</a>
          </p>
          <h3>内容责任人（依《国家州际媒体协议》§18 第 2 款）</h3>
          <p>王雪松 (Wang Xuesong)，地址同上。</p>
          <h3>在线纠纷解决</h3>
          <p>
            欧盟委员会提供在线纠纷解决平台：
            <a href="https://ec.europa.eu/consumers/odr" target="_blank" rel="noopener noreferrer">
              https://ec.europa.eu/consumers/odr
            </a>
            。我们的邮箱见上。我们没有义务、也不愿意参与消费者仲裁机构的纠纷解决程序。
          </p>
          <h3>免责声明</h3>
          <p>
            PMET 是一款用于成对 motif 富集分析的科研工具，**不提供任何医学、诊断或临床建议**。
            尽管我们已尽力核对内容，对外部链接的内容不承担责任，相关页面由其运营者全权负责。
          </p>
        </section>
      )}
    </article>
  );
}
