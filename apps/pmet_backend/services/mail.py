import html
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from datetime import datetime
from pathlib import Path

from ..config import config


MODE_LABELS = {
    "promoters_pre": "Pre-computed promoters",
    "promoters": "Full promoters",
    "intervals": "Intervals",
}


class MailService:
    """Email notification service."""

    def __init__(self):
        self.username = config.EMAIL_USERNAME
        self.password = config.EMAIL_PASSWORD
        self.address = config.EMAIL_ADDRESS
        self.server = config.EMAIL_SERVER
        self.port = int(config.EMAIL_PORT) if config.EMAIL_PORT else 587

    def _send_email(self, to: str, subject: str, body: str, html_body: bool = True):
        if not all([self.username, self.password, self.server]):
            print(f"Email not configured, skipping send to {to}")
            return False

        msg = MIMEMultipart("alternative")
        msg["From"] = self.address
        msg["To"] = to
        msg["Subject"] = subject

        msg.attach(MIMEText(body, "html" if html_body else "plain"))

        try:
            with smtplib.SMTP(self.server, self.port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.sendmail(self.address, to, msg.as_string())
            return True
        except Exception as e:
            print(f"Failed to send email: {e}")
            return False

    def _escape(self, value) -> str:
        return html.escape(str(value), quote=True)

    def _timestamp(self) -> str:
        return datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    def _mode_label(self, mode: Optional[str]) -> str:
        return MODE_LABELS.get(mode or "", mode or "Unknown")

    def _humanize_identifier(self, value: Optional[str]) -> str:
        return (value or "").replace("_", " ")

    def _format_iso_time(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M UTC")
        except ValueError:
            return value

    def _runtime_range(self, task_meta: dict) -> Optional[str]:
        estimate = task_meta.get("runtime_estimate")
        if not isinstance(estimate, dict):
            return None

        lower = estimate.get("lower_seconds")
        upper = estimate.get("upper_seconds")
        if not isinstance(lower, (int, float)) or not isinstance(upper, (int, float)):
            return None

        if upper < 90:
            return f"{round(lower)} - {round(upper)} seconds"
        if upper < 60 * 90:
            return f"{max(1, round(lower / 60))} - {max(1, round(upper / 60))} minutes"
        return f"{lower / 3600:.1f} - {upper / 3600:.1f} hours"

    def _index_info(self, task_meta: dict) -> tuple[Optional[str], Optional[str]]:
        species = task_meta.get("indexing_species")
        motif_db = task_meta.get("indexing_motif_db")
        if species or motif_db:
            return species, motif_db

        premade = task_meta.get("premade_index")
        if not premade:
            return None, None
        parts = Path(str(premade)).parts
        try:
            idx = parts.index("precomputed_indexes")
        except ValueError:
            return None, None
        if len(parts) <= idx + 2:
            return None, None
        return parts[idx + 1], parts[idx + 2]

    def _row(self, label: str, value) -> str:
        if value is None or value == "":
            return ""
        return (
            "<tr>"
            f"<th>{self._escape(label)}</th>"
            f"<td>{self._escape(value)}</td>"
            "</tr>"
        )

    def _task_summary_rows(self, task_meta: dict, user_email: Optional[str] = None) -> str:
        species, motif_db = self._index_info(task_meta)
        estimate = self._runtime_range(task_meta)
        factors = task_meta.get("runtime_estimate", {}).get("factors", {})
        if not isinstance(factors, dict):
            factors = {}

        rows = [
            self._row("Task ID", task_meta.get("task_id")),
            self._row("User email", user_email),
            self._row("Analysis mode", self._mode_label(task_meta.get("mode"))),
            self._row("Created", self._format_iso_time(task_meta.get("created_at"))),
            self._row("Started", self._format_iso_time(task_meta.get("started_at"))),
            self._row("Completed", self._format_iso_time(task_meta.get("completed_at"))),
            self._row("Species", self._humanize_identifier(species) if species else None),
            self._row("Motif database", self._humanize_identifier(motif_db) if motif_db else None),
            self._row("Estimated runtime", estimate),
            self._row("Worker threads", factors.get("ncpu") or config.NCPU),
            self._row("Target genes / intervals", factors.get("n_target_genes") or factors.get("n_intervals")),
            self._row("Motifs", factors.get("n_motifs")),
        ]
        return "".join(row for row in rows if row)

    def _parameter_rows(self, task_meta: dict) -> str:
        rows = [
            self._row("IC threshold", task_meta.get("ic_threshold")),
            self._row("Max motif matches", task_meta.get("max_match")),
            self._row("Selected promoters", task_meta.get("promoter_num")),
            self._row("FIMO threshold", task_meta.get("fimo_threshold")),
            self._row("Promoter length", task_meta.get("promoter_length")),
            self._row("5' UTR included", task_meta.get("utr5")),
            self._row("Promoters overlap", task_meta.get("promoters_overlap")),
        ]
        return "".join(row for row in rows if row)

    def _input_rows(self, task_meta: dict) -> str:
        rows = [
            self._row("Gene / interval list", task_meta.get("genes_file")),
            self._row("Genome / interval FASTA", task_meta.get("fasta_file")),
            self._row("GFF3 annotation", task_meta.get("gff3_file")),
            self._row("Motif MEME file", task_meta.get("meme_file")),
            self._row("Pre-computed index", task_meta.get("premade_index")),
        ]
        return "".join(row for row in rows if row)

    def _table(self, title: str, rows: str) -> str:
        if not rows:
            return ""
        return f"""
        <h2>{self._escape(title)}</h2>
        <table>
            <tbody>{rows}</tbody>
        </table>
        """

    def _template(
        self,
        heading: str,
        intro: str,
        status: str,
        task_meta: dict,
        action_html: str = "",
        extra_html: str = "",
        user_email: Optional[str] = None,
    ) -> str:
        summary = self._table("Task summary", self._task_summary_rows(task_meta, user_email))
        params = self._table("Parameters", self._parameter_rows(task_meta))
        inputs = self._table("Inputs", self._input_rows(task_meta))
        generated = self._timestamp()

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
          <style>
            body {{
              margin: 0;
              background: #f8fafc;
              color: #0f172a;
              font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
              line-height: 1.5;
            }}
            .card {{
              max-width: 720px;
              margin: 24px auto;
              background: #ffffff;
              border: 1px solid #e2e8f0;
              border-radius: 12px;
              padding: 28px;
            }}
            .status {{
              display: inline-block;
              margin-bottom: 12px;
              border-radius: 999px;
              background: #ccfbf1;
              color: #0f766e;
              font-size: 12px;
              font-weight: 700;
              letter-spacing: .04em;
              padding: 4px 10px;
              text-transform: uppercase;
            }}
            h1 {{
              margin: 0 0 8px;
              font-size: 22px;
              color: #0f172a;
            }}
            h2 {{
              margin: 24px 0 8px;
              font-size: 14px;
              color: #334155;
              text-transform: uppercase;
              letter-spacing: .05em;
            }}
            p {{ margin: 8px 0; }}
            table {{
              width: 100%;
              border-collapse: collapse;
              border: 1px solid #e2e8f0;
              border-radius: 8px;
              overflow: hidden;
            }}
            th, td {{
              border-bottom: 1px solid #e2e8f0;
              padding: 9px 12px;
              text-align: left;
              vertical-align: top;
              font-size: 13px;
            }}
            tr:last-child th, tr:last-child td {{ border-bottom: 0; }}
            th {{
              width: 210px;
              background: #f8fafc;
              color: #64748b;
              font-weight: 600;
            }}
            td {{
              color: #0f172a;
              word-break: break-word;
            }}
            .button {{
              display: inline-block;
              margin-top: 14px;
              border-radius: 8px;
              background: #0f766e;
              color: #ffffff !important;
              padding: 10px 14px;
              text-decoration: none;
              font-weight: 700;
            }}
            .note {{
              margin-top: 22px;
              color: #64748b;
              font-size: 12px;
            }}
            .danger {{ background: #fee2e2; color: #b91c1c; }}
          </style>
        </head>
        <body>
          <div class="card">
            <div class="status">{self._escape(status)}</div>
            <h1>{self._escape(heading)}</h1>
            <p>{self._escape(intro)}</p>
            {action_html}
            {extra_html}
            {summary}
            {params}
            {inputs}
            <p class="note">Generated by PMET at {self._escape(generated)}.</p>
          </div>
        </body>
        </html>
        """

    def send_started_notification(self, email: str, task_meta):
        """Send notification when task starts."""
        meta = task_meta if isinstance(task_meta, dict) else {"task_id": task_meta}
        return self._send_email(
            email,
            f"PMET task started: {meta.get('task_id', '')}",
            self._template(
                "Your PMET analysis has started",
                "Your task is now running. We will email you again when the results are ready.",
                "Started",
                meta,
            ),
        )

    def send_result_notification(self, email: str, result_link: str, task_meta: Optional[dict] = None):
        """Send notification with result download link."""
        meta = task_meta or {}
        if result_link:
            safe_link = self._escape(result_link)
            action = f'<p><a class="button" href="{safe_link}">Download results</a></p>'
            extra = f'<p>Direct link: <a href="{safe_link}">{safe_link}</a></p>'
        else:
            action = ""
            extra = (
                '<p class="status danger">Download URL is not configured. '
                "Please contact the PMET administrator.</p>"
            )

        return self._send_email(
            email,
            f"PMET results ready: {meta.get('task_id', '')}",
            self._template(
                "Your PMET results are ready",
                "The analysis completed successfully and the result archive is available for download.",
                "Completed",
                meta,
                action_html=action,
                extra_html=extra,
            ),
        )

    def send_cancelled_notification(
        self,
        email: str,
        task_id: str,
        reason: Optional[str] = None,
        task_meta: Optional[dict] = None,
    ):
        """Notify the user that an admin terminated their task."""
        meta = dict(task_meta or {})
        meta.setdefault("task_id", task_id)
        reason_html = (
            f"<p><strong>Reason:</strong> {self._escape(reason)}</p>"
            if reason
            else "<p>No specific reason was provided. Please contact the administrator if you need details.</p>"
        )
        return self._send_email(
            email,
            f"PMET task cancelled: {meta.get('task_id', '')}",
            self._template(
                "Your PMET task was cancelled",
                "The administrator terminated this analysis before it completed.",
                "Cancelled",
                meta,
                extra_html=reason_html,
            ),
        )

    def send_admin_notification(self, user_email: str, task_meta: dict):
        """Send notification to admin about new task."""
        return self._send_email(
            self.username,
            f"PMET new task submitted: {task_meta.get('task_id', '')}",
            self._template(
                "New PMET task submitted",
                "A user submitted a PMET analysis task.",
                "Submitted",
                task_meta,
                user_email=user_email,
            ),
        )
