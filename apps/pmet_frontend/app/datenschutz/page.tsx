'use client';

// Datenschutzerklärung (DSGVO Art. 13/14 transparency).
// German is the legally binding version. English + 汉文 below are
// informational, switched by the user's current locale toggle.
//
// Numbers in §4 (30-day retention) reflect the configured
// result_retention_days default. Update there + here if you change it.

import { useTranslation } from '@/lib/i18n';

export default function DatenschutzPage() {
  const { locale } = useTranslation();

  return (
    <article className="prose prose-slate mx-auto max-w-3xl py-8">
      <section>
        <h1>Datenschutzerklärung</h1>
        <p className="text-sm text-slate-500">
          Verbindliche Fassung in deutscher Sprache. Stand: 2026-05-17.
        </p>

        <h2>1. Verantwortlicher</h2>
        <p>
          Wang Xuesong (王雪松)<br />
          Lynarstraße 26, 13353 Berlin, Deutschland<br />
          E-Mail: <a href="mailto:wangxuesong29@gmail.com">wangxuesong29@gmail.com</a>
        </p>
        <p>
          Für Anfragen zum Datenschutz wenden Sie sich bitte an dieselbe E-Mail-Adresse.
          Wir antworten innerhalb eines Monats.
        </p>

        <h2>2. Erhobene Daten</h2>
        <p>Wir verarbeiten die folgenden personenbezogenen Daten:</p>
        <ul>
          <li>
            <strong>E-Mail-Adresse</strong> — bei jeder Aufgabenübertragung geben Sie eine
            E-Mail-Adresse an, damit wir Sie nach Abschluss der Analyse benachrichtigen können.
          </li>
          <li>
            <strong>IP-Adresse</strong> — bei jedem Aufruf wird die IP-Adresse des anfragenden
            Geräts protokolliert. <em>IP-Adressen werden vor der Speicherung anonymisiert</em>:
            bei IPv4 wird das letzte Oktett auf null gesetzt, bei IPv6 die letzten 64 Bit.
          </li>
          <li>
            <strong>Hochgeladene Dateien</strong> — FASTA-, GFF3-, MEME- und Gen-Listen-Dateien
            sowie die zugehörigen Analyseparameter (z. B. IC-Schwellenwert), die Sie zur
            Auswertung übermitteln.
          </li>
          <li>
            <strong>Aufgaben-Metadaten</strong> — ID, Status, Erstellungs- und
            Abschlusszeitpunkt, ausgewählter Analysemodus, etwaige Fehlermeldungen.
          </li>
        </ul>

        <h2>3. Rechtsgrundlagen</h2>
        <ul>
          <li>
            <strong>Art. 6 Abs. 1 lit. b DSGVO (Vertragserfüllung)</strong> — für
            E-Mail-Adresse, hochgeladene Dateien und Aufgaben-Metadaten. Diese Verarbeitung
            ist erforderlich, um die von Ihnen angeforderte Analyse durchzuführen und das
            Ergebnis bereitzustellen.
          </li>
          <li>
            <strong>Art. 6 Abs. 1 lit. f DSGVO (berechtigte Interessen)</strong> — für
            anonymisierte IP-Adressen in Server- und Admin-Audit-Logs. Berechtigtes
            Interesse: Sicherheit der Anwendung, Verhinderung von Missbrauch (z. B.
            Brute-Force-Angriffen auf den Admin-Login), Fehlerdiagnose.
          </li>
        </ul>

        <h2>4. Speicherdauer</h2>
        <ul>
          <li>
            <strong>Aufgaben-Ergebnisse, hochgeladene Dateien, zugehörige E-Mail-Adresse</strong>:{' '}
            <strong>30 Tage</strong> ab Erstellung der Aufgabe; danach automatische Löschung.
          </li>
          <li>
            <strong>Admin-Audit-Logs (anonymisierte IPs)</strong>: 30 Tage; ältere Einträge
            werden überschrieben.
          </li>
          <li>
            <strong>Server-Zugriffsprotokolle</strong>: gemäß üblicher Aufbewahrungsfristen
            des verwendeten Betriebssystems / der Netzwerk-Edge.
          </li>
        </ul>

        <h2>5. Verarbeitungsort und Auftragsverarbeiter</h2>
        <p>
          Die Hauptverarbeitung — Speicherung, Ausführung der Analyse und Versand der
          Ergebnis-Benachrichtigung — erfolgt auf einem von uns betriebenen Server in{' '}
          <strong>Berlin, Deutschland</strong>. Wir nutzen folgende Auftragsverarbeiter
          bzw. Drittanbieter:
        </p>
        <ul>
          <li>
            <strong>DigitalOcean LLC</strong> — Rechenzentrum Frankfurt am Main, Deutschland.
            Funktion: Netzwerk-Ingress und TLS-Terminierung (Reverse-Proxy). Es findet keine
            dauerhafte Speicherung Ihrer Nutzdaten auf der DigitalOcean-Infrastruktur statt.
            Verarbeitung erfolgt ausschließlich innerhalb der EU.
          </li>
          <li>
            <strong>Google LLC (USA)</strong> — über den Gmail-SMTP-Versand-Service für die
            Ergebnis-Benachrichtigungs-E-Mail. Wenn Sie eine E-Mail-Adresse angeben, wird
            diese an Google übermittelt. Die Übermittlung in die USA erfolgt auf Grundlage des{' '}
            <em>EU-US Data Privacy Framework</em>.
          </li>
        </ul>

        <h2>6. Ihre Rechte</h2>
        <p>Sie haben jederzeit das Recht auf:</p>
        <ul>
          <li>Auskunft über die zu Ihrer Person gespeicherten Daten (Art. 15 DSGVO)</li>
          <li>Berichtigung unrichtiger Daten (Art. 16 DSGVO)</li>
          <li>Löschung (Art. 17 DSGVO)</li>
          <li>Einschränkung der Verarbeitung (Art. 18 DSGVO)</li>
          <li>Datenübertragbarkeit (Art. 20 DSGVO)</li>
          <li>Widerspruch gegen die Verarbeitung (Art. 21 DSGVO)</li>
        </ul>
        <p>
          Zur Ausübung wenden Sie sich bitte an die unter §1 genannte E-Mail-Adresse mit
          einem Hinweis auf die Aufgaben-ID, die Sie betrifft.
        </p>

        <h2>7. Beschwerderecht</h2>
        <p>
          Sie haben das Recht, sich bei einer Datenschutz-Aufsichtsbehörde zu beschweren. Die
          für uns zuständige Behörde ist die{' '}
          <strong>Berliner Beauftragte für Datenschutz und Informationsfreiheit</strong>,
          Friedrichstraße 219, 10969 Berlin —{' '}
          <a href="https://www.datenschutz-berlin.de/" target="_blank" rel="noopener noreferrer">
            datenschutz-berlin.de
          </a>
          .
        </p>

        <h2>8. Cookies und lokaler Speicher</h2>
        <p>
          Diese Anwendung verwendet ausschließlich technisch notwendige Cookies und
          LocalStorage-Einträge. Eine gesonderte Einwilligung gemäß § 25 Abs. 1 TTDSG ist
          daher nicht erforderlich (Ausnahme nach § 25 Abs. 2 Nr. 2 TTDSG).
        </p>
        <ul>
          <li>
            <code>pmet_admin</code> (httpOnly-Cookie) — nur bei Admin-Login gesetzt, enthält
            eine zufällige Session-ID (kein dauerhaft gültiger Token). Lebensdauer: 30 Tage.
          </li>
          <li>
            <code>pmet_locale</code> (LocalStorage) — speichert die gewählte Anzeigesprache
            (en oder zh). Wird nicht an den Server übermittelt.
          </li>
        </ul>

        <h2>9. Änderungen dieser Erklärung</h2>
        <p>
          Wir behalten uns vor, diese Datenschutzerklärung anzupassen, sofern dies aufgrund
          neuer Funktionen oder gesetzlicher Änderungen erforderlich wird. Die jeweils
          aktuelle Fassung ist stets auf dieser Seite abrufbar.
        </p>
      </section>

      {/* ---------------- English ---------------- */}
      {locale === 'en' && (
        <>
          <hr className="my-10" />
          <section>
            <h2 className="text-base font-semibold uppercase tracking-wider text-slate-500">
              English translation (informational)
            </h2>

            <h3>1. Controller</h3>
            <p>
              Wang Xuesong (王雪松)<br />
              Lynarstraße 26, 13353 Berlin, Germany<br />
              E-mail: <a href="mailto:wangxuesong29@gmail.com">wangxuesong29@gmail.com</a>
            </p>
            <p>
              For data-protection enquiries please use the same address. We respond within
              one month.
            </p>

            <h3>2. Data we process</h3>
            <ul>
              <li>
                <strong>Email address</strong> — supplied with every submission so we can
                notify you when the analysis finishes.
              </li>
              <li>
                <strong>IP address</strong> — recorded on each request. <em>IPs are
                anonymised before storage</em>: IPv4 last octet zeroed, IPv6 last 64 bits
                zeroed.
              </li>
              <li>
                <strong>Uploaded files</strong> — FASTA, GFF3, MEME, gene-list files plus the
                associated analysis parameters (e.g. IC threshold) you submit.
              </li>
              <li>
                <strong>Task metadata</strong> — ID, status, creation / completion
                timestamps, selected mode, any error messages.
              </li>
            </ul>

            <h3>3. Legal bases</h3>
            <ul>
              <li>
                <strong>Art. 6(1)(b) GDPR (contract performance)</strong> — for email,
                uploaded files, task metadata. The processing is necessary to perform the
                analysis you requested and deliver the result.
              </li>
              <li>
                <strong>Art. 6(1)(f) GDPR (legitimate interests)</strong> — for anonymised
                IPs in server and admin-audit logs. Legitimate interest: keeping the service
                secure, preventing abuse (e.g. brute-force attacks on the admin login), and
                debugging.
              </li>
            </ul>

            <h3>4. Retention</h3>
            <ul>
              <li>
                <strong>Task outputs, uploaded files, associated email</strong>:{' '}
                <strong>30 days</strong> from task creation, then automatic deletion.
              </li>
              <li>
                <strong>Admin audit log (anonymised IPs)</strong>: 30 days, oldest records
                overwritten.
              </li>
              <li>
                <strong>Server access logs</strong>: according to the host OS / network edge
                defaults.
              </li>
            </ul>

            <h3>5. Processing location and processors</h3>
            <p>
              Primary processing — storage, running the analysis, sending the result email —
              happens on a server we operate in <strong>Berlin, Germany</strong>.
              Processors and third parties used:
            </p>
            <ul>
              <li>
                <strong>DigitalOcean LLC</strong> — Frankfurt data centre, Germany. Function:
                network ingress and TLS termination (reverse proxy). No persistent storage
                of user data on DigitalOcean infrastructure. Processing remains within the
                EU.
              </li>
              <li>
                <strong>Google LLC (USA)</strong> — Gmail SMTP service for the result
                notification email. If you supply an email address, it is forwarded to
                Google. Transfer to the US relies on the <em>EU-US Data Privacy Framework</em>.
              </li>
            </ul>

            <h3>6. Your rights</h3>
            <p>You always have the right to:</p>
            <ul>
              <li>Access the data we hold about you (Art. 15 GDPR)</li>
              <li>Correction of inaccurate data (Art. 16 GDPR)</li>
              <li>Erasure (Art. 17 GDPR)</li>
              <li>Restriction of processing (Art. 18 GDPR)</li>
              <li>Data portability (Art. 20 GDPR)</li>
              <li>Object to processing (Art. 21 GDPR)</li>
            </ul>
            <p>
              To exercise, email the address in §1 with the task ID this concerns.
            </p>

            <h3>7. Right to lodge a complaint</h3>
            <p>
              You have the right to lodge a complaint with a data-protection supervisory
              authority. The authority responsible for us is the{' '}
              <strong>Berlin Commissioner for Data Protection and Freedom of Information</strong>,
              Friedrichstraße 219, 10969 Berlin —{' '}
              <a href="https://www.datenschutz-berlin.de/" target="_blank" rel="noopener noreferrer">
                datenschutz-berlin.de
              </a>
              .
            </p>

            <h3>8. Cookies and local storage</h3>
            <p>
              This application uses only strictly necessary cookies / localStorage entries.
              Separate consent under § 25(1) TTDSG is therefore not required (exception per
              § 25(2)(2) TTDSG).
            </p>
            <ul>
              <li>
                <code>pmet_admin</code> (httpOnly cookie) — set only after admin login,
                carries a random session ID (not a long-lived token). Lifetime: 30 days.
              </li>
              <li>
                <code>pmet_locale</code> (localStorage) — stores the chosen display language
                (en or zh). Not transmitted to the server.
              </li>
            </ul>

            <h3>9. Changes</h3>
            <p>
              We may update this notice as features or applicable law change. The current
              version is always at this URL.
            </p>
          </section>
        </>
      )}

      {/* ---------------- 汉文 ---------------- */}
      {locale === 'zh' && (
        <>
          <hr className="my-10" />
          <section>
            <h2 className="text-base font-semibold uppercase tracking-wider text-slate-500">
              汉文翻译（仅供参考）
            </h2>

            <h3>1. 数据控制者</h3>
            <p>
              王雪松 (Wang Xuesong)<br />
              Lynarstraße 26, 13353 柏林, 德国<br />
              电子邮件：<a href="mailto:wangxuesong29@gmail.com">wangxuesong29@gmail.com</a>
            </p>
            <p>
              数据保护相关咨询请发上述邮箱。我们将在一个月内回复。
            </p>

            <h3>2. 我们处理哪些数据</h3>
            <ul>
              <li>
                <strong>电子邮件地址</strong> —— 每次提交任务时由您填写，用于在分析完成后通知您。
              </li>
              <li>
                <strong>IP 地址</strong> —— 每次请求会被记录。<em>IP 在存储前已匿名化</em>：
                IPv4 末段置零、IPv6 末 64 位置零。
              </li>
              <li>
                <strong>上传文件</strong> —— 您提交的 FASTA / GFF3 / MEME / 基因列表 文件，
                以及对应的分析参数（如 IC 阈值）。
              </li>
              <li>
                <strong>任务元数据</strong> —— ID、状态、创建 / 完成时间戳、所选模式、错误信息（若有）。
              </li>
            </ul>

            <h3>3. 法律依据</h3>
            <ul>
              <li>
                <strong>GDPR 第 6 条第 1 款第 b 项（合同履行）</strong> —— 用于邮箱、上传文件、
                任务元数据。这是完成您所请求的分析并交付结果所必需的处理。
              </li>
              <li>
                <strong>GDPR 第 6 条第 1 款第 f 项（合法利益）</strong> —— 用于服务器日志和
                管理员审计日志中的匿名 IP。合法利益：保证服务安全、防止滥用（如管理员登录爆破）、
                故障诊断。
              </li>
            </ul>

            <h3>4. 保留期限</h3>
            <ul>
              <li>
                <strong>任务结果、上传文件、关联邮箱</strong>：自任务创建起 <strong>30 天</strong>，
                之后自动删除。
              </li>
              <li>
                <strong>管理员审计日志（匿名 IP）</strong>：30 天，更早的记录会被覆盖。
              </li>
              <li>
                <strong>服务器访问日志</strong>：依操作系统 / 网络入口默认保留周期。
              </li>
            </ul>

            <h3>5. 处理地点与子处理者</h3>
            <p>
              主要处理 —— 存储、运行分析、发送结果通知 —— 发生在我们运营的、位于
              <strong>德国柏林</strong>的服务器上。我们使用的子处理者 / 第三方服务：
            </p>
            <ul>
              <li>
                <strong>DigitalOcean LLC</strong> —— 法兰克福数据中心，德国。
                作用：网络入口与 TLS 终止（反向代理）。您的用户数据**不会**在 DigitalOcean
                基础设施上持久存储。处理过程不离开欧盟。
              </li>
              <li>
                <strong>Google LLC（美国）</strong> —— 通过 Gmail SMTP 服务发送结果通知邮件。
                您填写邮箱后，该邮箱会被转发给 Google。向美国的数据传输依据是
                <em>欧盟-美国数据隐私框架（EU-US Data Privacy Framework）</em>。
              </li>
            </ul>

            <h3>6. 您的权利</h3>
            <p>您随时享有以下权利：</p>
            <ul>
              <li>访问我们保存的关于您的数据（GDPR 第 15 条）</li>
              <li>更正不准确的数据（GDPR 第 16 条）</li>
              <li>删除（GDPR 第 17 条）</li>
              <li>限制处理（GDPR 第 18 条）</li>
              <li>数据可携带（GDPR 第 20 条）</li>
              <li>反对处理（GDPR 第 21 条）</li>
            </ul>
            <p>
              行使方式：通过 §1 中的邮箱联系我们，并附上相关任务 ID。
            </p>

            <h3>7. 投诉权</h3>
            <p>
              您有权向数据保护监管机构投诉。对我们具有管辖权的是
              <strong>柏林数据保护与信息自由专员（Berliner Beauftragte für Datenschutz und
              Informationsfreiheit）</strong>，地址：Friedrichstraße 219, 10969 Berlin —{' '}
              <a href="https://www.datenschutz-berlin.de/" target="_blank" rel="noopener noreferrer">
                datenschutz-berlin.de
              </a>
              。
            </p>

            <h3>8. Cookie 与本地存储</h3>
            <p>
              本应用仅使用技术必需的 cookie / localStorage 条目，因此**不需要**依
              §25 TTDSG 第 1 款单独取得同意（适用 §25 第 2 款第 2 项的例外）。
            </p>
            <ul>
              <li>
                <code>pmet_admin</code>（httpOnly cookie） —— 仅在管理员登录后设置，
                内容是一个随机 session ID（**不是**长期有效的 token）。寿命：30 天。
              </li>
              <li>
                <code>pmet_locale</code>（localStorage） —— 保存所选显示语言（en 或 zh），
                **不**向服务器传输。
              </li>
            </ul>

            <h3>9. 本声明的变更</h3>
            <p>
              当功能或法规变化时，我们可能更新本声明。当前版本始终可在此 URL 访问。
            </p>
          </section>
        </>
      )}
    </article>
  );
}
