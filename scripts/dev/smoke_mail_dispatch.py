#!/usr/bin/env python3
"""One-shot smoke test for the three status-aware mail templates.

Sends three real emails (completed-with-notes / partial_success / failed)
to a single recipient so we can eyeball Gmail rendering — the unit test
asserts strings, but only a real client tells us whether the inline-CSS
amber Notes block, action button, and Subject character set survive.

Run:
    python3 scripts/dev/smoke_mail_dispatch.py wangxuesong29@gmail.com

Reads SMTP creds from data/configure/email_credential.txt the same way
the worker does. Prints a tagged log line per send. Exits non-zero on
any send failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "apps"))

from pmet_backend.services.mail import MailService  # noqa: E402


def make_meta(task_id: str) -> dict:
    return {
        "task_id": task_id,
        "mode": "promoters_pre",
        "email": "smoketest@local",
        "created_at": "2026-05-01T10:00:00",
        "started_at": "2026-05-01T10:00:01",
        "completed_at": "2026-05-01T10:05:00",
    }


def main(recipient: str) -> int:
    mail = MailService()
    if not all([mail.username, mail.password, mail.server]):
        print("ERROR: SMTP creds not loaded — check data/configure/email_credential.txt")
        return 2

    print(f"Sending three smoke emails to {recipient} via {mail.server}:{mail.port}")

    failures: list[str] = []

    # 1. Completed with notes (merged path — was completed_with_warnings).
    ok = mail.send_result_notification(
        recipient,
        "https://pmet.online/results/smoketest_completed.zip",
        make_meta("smoketest_completed"),
        warnings=["heatmap: rendered with caveats; output may have minor visual artifacts"],
    )
    print(f"[1/3] completed (with notes): {'OK' if ok else 'FAIL'}")
    if not ok:
        failures.append("completed-with-notes")

    # 2. Partial success — pairing OK, late-stage crash.
    ok = mail.send_partial_result_notification(
        recipient,
        "https://pmet.online/api/tasks/smoketest_partial/partial-result",
        "Error in `ggsave()`: ! Dimensions exceed 50 inches",
        [
            "heatmap: rendering failed; motif_output.txt is complete",
            "zip: late-stage failure; partial result still available",
        ],
        make_meta("smoketest_partial"),
    )
    print(f"[2/3] partial_success: {'OK' if ok else 'FAIL'}")
    if not ok:
        failures.append("partial_success")

    # 3. Hard failure — no usable output.
    ok = mail.send_failed_notification(
        recipient,
        "Error: No genes from the input list match the index universe (0/512 matched)",
        make_meta("smoketest_failed"),
    )
    print(f"[3/3] failed: {'OK' if ok else 'FAIL'}")
    if not ok:
        failures.append("failed")

    if failures:
        print(f"\nFAILURES: {', '.join(failures)}")
        return 1
    print("\nAll three sent. Check the inbox to verify rendering.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: smoke_mail_dispatch.py <recipient_email>", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
