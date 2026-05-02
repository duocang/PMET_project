#!/usr/bin/env python3
"""Unit tests for MailService dispatch (Problem 4 follow-up: status-aware
emails, including the partial-success path that surfaces a direct
motif_output.txt download link).

The MailService base talks to SMTP, but we stub out
`MailService._send_email` so nothing leaves the test process. We then
assert: the right Subject, the presence of the partial / zip download
link in the body, and the warnings block when applicable.

Companion to `test_stage_status.py` — that one tests the status
derivation in isolation; this one tests that the worker mail templates
do the right thing given an effective_status output.

Run via tests/unit/run.sh.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "apps"))

from pmet_backend.services.mail import MailService  # noqa: E402


SAMPLE_META = {
    "task_id": "pmet_dispatchtest",
    "mode": "promoters_pre",
    "email": "user@example.com",
    "created_at": "2026-05-01T10:00:00",
    "started_at": "2026-05-01T10:00:01",
    "completed_at": "2026-05-01T10:05:00",
}


class MailDispatchTests(unittest.TestCase):
    def setUp(self):
        self.mail = MailService()
        # Patch the actual SMTP send so nothing leaves the process.
        # We capture (to, subject, body) to make assertions.
        self.sent: list[tuple[str, str, str]] = []
        self._patcher = patch.object(
            MailService, "_send_email",
            side_effect=lambda to, subject, body, html_body=True: (
                self.sent.append((to, subject, body)) or True
            ),
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    # ------------------------------------------------------------------
    # send_result_notification: clean and with-warnings variants
    # ------------------------------------------------------------------
    def test_result_notification_clean(self):
        self.mail.send_result_notification(
            "u@example.com",
            "https://example.com/results/pmet_x.zip",
            SAMPLE_META,
        )
        self.assertEqual(len(self.sent), 1)
        to, subject, body = self.sent[0]
        self.assertEqual(to, "u@example.com")
        self.assertIn("PMET results ready", subject)
        self.assertNotIn("with notes", subject)
        # Body has a download button that points at the zip
        self.assertIn("pmet_x.zip", body)
        # No warnings block
        self.assertNotIn("Notes:</strong>", body)
        # Status pill is success-toned (green), not amber/red
        self.assertIn('class="status success"', body)

    def test_result_notification_with_warnings(self):
        self.mail.send_result_notification(
            "u@example.com",
            "https://example.com/results/pmet_x.zip",
            SAMPLE_META,
            warnings=["heatmap: rendering had caveats"],
        )
        to, subject, body = self.sent[-1]
        self.assertIn("with notes", subject)
        self.assertIn("Completed (with notes)", body)
        self.assertIn("heatmap: rendering had caveats", body)
        self.assertIn("pmet_x.zip", body)
        # With-notes pill is amber, not green
        self.assertIn('class="status warning"', body)

    # ------------------------------------------------------------------
    # send_partial_result_notification
    # ------------------------------------------------------------------
    def test_partial_result_notification(self):
        self.mail.send_partial_result_notification(
            "u@example.com",
            "https://example.com/api/tasks/pmet_x/partial-result",
            "Error in `ggsave()`: ! Dimensions exceed 50 inches",
            ["heatmap: rendering failed; motif_output.txt is complete",
             "zip: late-stage failure; partial result still available"],
            SAMPLE_META,
        )
        to, subject, body = self.sent[-1]
        self.assertEqual(to, "u@example.com")
        # Subject must NOT say "ready" or "failed" alone — it's a partial
        self.assertIn("partial result", subject.lower())
        # Body advertises the partial-result endpoint
        self.assertIn("/api/tasks/pmet_x/partial-result", body)
        self.assertIn("motif_output.txt", body)
        # Error summary makes it through
        self.assertIn("ggsave", body)
        # Warnings block listed
        self.assertIn("rendering failed", body)
        # Status badge says Partial success, in amber
        self.assertIn("Partial success", body)
        self.assertIn('class="status warning"', body)

    def test_partial_result_notification_without_link(self):
        """Defensive: PUBLIC_BASE_URL unset → empty partial_link → email
        still sends with a warning block instead of a button."""
        self.mail.send_partial_result_notification(
            "u@example.com",
            "",  # no public URL configured
            "some error",
            ["heatmap: failed"],
            SAMPLE_META,
        )
        _, _, body = self.sent[-1]
        self.assertIn("not configured", body)
        self.assertNotIn('class="button"', body)

    # ------------------------------------------------------------------
    # send_failed_notification
    # ------------------------------------------------------------------
    def test_failed_notification(self):
        self.mail.send_failed_notification(
            "u@example.com",
            "No genes from the input list match the index universe",
            SAMPLE_META,
        )
        to, subject, body = self.sent[-1]
        self.assertEqual(to, "u@example.com")
        self.assertIn("PMET task failed", subject)
        # Status badge says Failed, in red
        self.assertIn("Failed", body)
        self.assertIn('class="status danger"', body)
        # Error summary present
        self.assertIn("match the index universe", body)
        # Common-causes checklist present
        self.assertIn("Common causes", body)
        self.assertIn("Gene IDs", body)


# ----------------------------------------------------------------------
# _build_partial_result_link is a worker helper that turns
# PUBLIC_BASE_URL (the bare-domain deployment URL, e.g.
# https://pmet.online) into the partial-result API URL. Validate it
# independently because the worker imports it into a celery task we
# don't want to instantiate in a unit test.
# ----------------------------------------------------------------------
class BuildPartialLinkTests(unittest.TestCase):
    def setUp(self):
        from pmet_backend.worker.tasks import pmet as pmet_task
        self.fn = pmet_task._build_partial_result_link
        self.config_mod = pmet_task.config

    def _with_public_base_url(self, value):
        return patch.object(self.config_mod, "PUBLIC_BASE_URL", value)

    def test_https(self):
        with self._with_public_base_url("https://pmet.online"):
            self.assertEqual(
                self.fn("pmet_abc"),
                "https://pmet.online/api/tasks/pmet_abc/partial-result",
            )

    def test_http_no_trailing_slash(self):
        with self._with_public_base_url("http://localhost:5960"):
            self.assertEqual(
                self.fn("pmet_xyz"),
                "http://localhost:5960/api/tasks/pmet_xyz/partial-result",
            )

    def test_trailing_slash_tolerated(self):
        with self._with_public_base_url("https://pmet.online/"):
            self.assertEqual(
                self.fn("pmet_x"),
                "https://pmet.online/api/tasks/pmet_x/partial-result",
            )

    def test_empty_returns_empty(self):
        with self._with_public_base_url(""):
            self.assertEqual(self.fn("pmet_x"), "")

    def test_unparseable_returns_empty(self):
        with self._with_public_base_url("not-a-url"):
            self.assertEqual(self.fn("pmet_x"), "")


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = unittest.TestSuite([
        loader.loadTestsFromTestCase(MailDispatchTests),
        loader.loadTestsFromTestCase(BuildPartialLinkTests),
    ])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
