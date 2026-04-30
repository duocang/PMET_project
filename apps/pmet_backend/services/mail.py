import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from datetime import datetime

from ..config import config


class MailService:
    """Email notification service"""

    def __init__(self):
        self.username = config.EMAIL_USERNAME
        self.password = config.EMAIL_PASSWORD
        self.address = config.EMAIL_ADDRESS
        self.server = config.EMAIL_SERVER
        self.port = int(config.EMAIL_PORT) if config.EMAIL_PORT else 587

    def _send_email(self, to: str, subject: str, body: str, html: bool = True):
        """Send an email"""
        if not all([self.username, self.password, self.server]):
            print(f"Email not configured, skipping send to {to}")
            return False

        msg = MIMEMultipart("alternative")
        msg["From"] = self.address
        msg["To"] = to
        msg["Subject"] = subject

        if html:
            msg.attach(MIMEText(body, "html"))
        else:
            msg.attach(MIMEText(body, "plain"))

        try:
            with smtplib.SMTP(self.server, self.port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.sendmail(self.address, to, msg.as_string())
            return True
        except Exception as e:
            print(f"Failed to send email: {e}")
            return False

    def send_started_notification(self, email: str, task_id: str):
        """Send notification when task starts"""
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; }}
                .card {{ max-width: 640px; margin: 20px auto; background: #ffffff; border-radius: 12px; padding: 24px; }}
                .header {{ color: #0f766e; font-size: 18px; margin-bottom: 16px; }}
            </style>
        </head>
        <body>
            <div class="card">
                <h1 class="header">Task Started</h1>
                <p>Your PMET analysis has started.</p>
                <p>Task ID: {task_id}</p>
                <p>We will notify you when results are ready.</p>
                <p style="color: #64748b; font-size: 13px;">Start time: {ts}</p>
            </div>
        </body>
        </html>
        """
        return self._send_email(email, "Your PMET task has started", body)

    def send_result_notification(self, email: str, result_link: str):
        """Send notification with result download link"""
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        link_block = (
            f'<p><a class="link" href="{result_link}">{result_link}</a></p>'
            if result_link
            else '<p style="color:#b91c1c;">Download URL is not configured on the server — please contact the administrator.</p>'
        )
        body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; }}
                .card {{ max-width: 640px; margin: 20px auto; background: #ffffff; border-radius: 12px; padding: 24px; }}
                .header {{ color: #0f766e; font-size: 18px; margin-bottom: 16px; }}
                .link {{ color: #2563eb; text-decoration: none; }}
            </style>
        </head>
        <body>
            <div class="card">
                <h1 class="header">Results Ready</h1>
                <p>Your PMET results are ready for download:</p>
                {link_block}
                <p style="color: #64748b; font-size: 13px;">Results remain available for one week.</p>
                <p style="color: #64748b; font-size: 13px;">Completed: {ts}</p>
            </div>
        </body>
        </html>
        """
        return self._send_email(email, "Your PMET results are ready", body)

    def send_cancelled_notification(
        self, email: str, task_id: str, reason: Optional[str] = None
    ):
        """Notify the user that an admin terminated their task.

        ``reason`` is optional; if absent the email falls back to a generic
        line so we never send an empty "<reason>" placeholder.
        """
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        reason_block = (
            f'<p><strong>Reason:</strong> {reason}</p>'
            if reason
            else '<p>No specific reason was provided. Please contact the administrator if you need details.</p>'
        )
        body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; }}
                .card {{ max-width: 640px; margin: 20px auto; background: #ffffff; border-radius: 12px; padding: 24px; }}
                .header {{ color: #b91c1c; font-size: 18px; margin-bottom: 16px; }}
                .id {{ font-family: monospace; background: #f1f5f9; padding: 2px 6px; border-radius: 4px; }}
            </style>
        </head>
        <body>
            <div class="card">
                <h1 class="header">Your PMET task was cancelled</h1>
                <p>The administrator has terminated your analysis.</p>
                <p>Task ID: <span class="id">{task_id}</span></p>
                {reason_block}
                <p>You can re-submit a new task any time.</p>
                <p style="color: #64748b; font-size: 13px;">Cancelled at: {ts}</p>
            </div>
        </body>
        </html>
        """
        return self._send_email(email, "Your PMET task was cancelled", body)

    def send_admin_notification(self, user_email: str, task_meta: dict):
        """Send notification to admin about new task"""
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; }}
                .card {{ max-width: 640px; margin: 20px auto; background: #ffffff; border-radius: 12px; padding: 24px; }}
                .header {{ color: #0f766e; font-size: 18px; margin-bottom: 16px; }}
                .param {{ background: #f1f5f9; padding: 8px 12px; border-radius: 6px; font-family: monospace; margin: 4px 0; }}
            </style>
        </head>
        <body>
            <div class="card">
                <h1 class="header">New Task Submitted</h1>
                <p><strong>User:</strong> {user_email}</p>
                <p><strong>Mode:</strong> {task_meta.get('mode')}</p>
                <p><strong>Task ID:</strong> {task_meta.get('task_id')}</p>
                <p><strong>Submitted:</strong> {ts}</p>
                <hr>
                <p><strong>Parameters:</strong></p>
                <div class="param">IC Threshold: {task_meta.get('ic_threshold')}</div>
                <div class="param">Max Match: {task_meta.get('max_match')}</div>
                <div class="param">FIMO Threshold: {task_meta.get('fimo_threshold')}</div>
                <div class="param">Threads: {config.NCPU}</div>
            </div>
        </body>
        </html>
        """
        return self._send_email(self.username, "PMET: New Task Submitted", body)
