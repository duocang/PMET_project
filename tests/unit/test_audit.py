#!/usr/bin/env python3
"""Unit tests for services/audit.py — admin operation audit trail.

The audit log is append-only JSONL at CONFIGURE_DIR/admin_audit.jsonl.
It records:

  - admin login attempts (success + failure)
  - settings PUT / cleanup runs / token rotation
  - mail send attempts (separate category)

These tests pin the contract every caller depends on:

  1. emit() never raises, even on disk failure (audit failures must
     not take down the action being audited)
  2. Records are JSON Lines — one record per line, newest writes go
     to the tail
  3. read_tail returns newest-first (audit panels render this way)
  4. category filter is in-memory (cheap; no per-line scan strategy)
  5. Rotation at 5 MB: the active file gets renamed to .jsonl.1 and
     a fresh one starts (operator can still inspect history)
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "apps"))

from pmet_backend.config import config  # noqa: E402
from pmet_backend.services import audit  # noqa: E402


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pmet_audit_test_"))
        self.cfg_patch = patch.object(config, "CONFIGURE_DIR", self.tmp)
        self.cfg_patch.start()

    def tearDown(self):
        self.cfg_patch.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ------------------------------------------------------------------
    # emit
    # ------------------------------------------------------------------
    def test_emit_writes_one_jsonline_per_call(self):
        audit.emit(action="login_ok", ok=True, ip="1.2.3.4")
        audit.emit(action="logout", ok=True, ip="1.2.3.4")
        lines = (self.tmp / "admin_audit.jsonl").read_text().splitlines()
        self.assertEqual(len(lines), 2)
        rec0 = json.loads(lines[0])
        rec1 = json.loads(lines[1])
        self.assertEqual(rec0["action"], "login_ok")
        self.assertEqual(rec1["action"], "logout")
        self.assertEqual(rec0["category"], "admin")  # default category
        self.assertTrue(rec0["ts"].endswith("Z"))  # UTC marker preserved

    def test_emit_captures_target_and_detail(self):
        audit.emit(
            action="task_terminate",
            ok=True,
            ip="10.0.0.1",
            target="phase1_abc",
            detail={"reason": "operator request"},
        )
        rec = json.loads((self.tmp / "admin_audit.jsonl").read_text().strip())
        self.assertEqual(rec["target"], "phase1_abc")
        self.assertEqual(rec["detail"]["reason"], "operator request")

    def test_emit_never_raises_on_disk_failure(self):
        """If the audit file can't be written we must NOT crash the
        action being audited. We simulate a permission error by
        pointing CONFIGURE_DIR at a path we can't create children in.
        """
        # On macOS / Linux, /dev/null/anything is guaranteed to be a
        # write-denied path.
        with patch.object(config, "CONFIGURE_DIR", Path("/dev/null/cannot-write")):
            # No exception → contract met. We don't assert *what* happened.
            audit.emit(action="login_ok", ok=True, ip="1.2.3.4")

    def test_emit_separate_category_for_mail(self):
        audit.emit(category="mail", action="send_ok", target="u@x.test")
        audit.emit(category="admin", action="login_ok", ip="1.2.3.4")
        records = audit.read_tail(n=10, category="mail")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["action"], "send_ok")

    # ------------------------------------------------------------------
    # read_tail
    # ------------------------------------------------------------------
    def test_read_tail_returns_newest_first(self):
        for i in range(5):
            audit.emit(action=f"action_{i}", ip="1.1.1.1")
        records = audit.read_tail(n=10)
        # File writes were chronological 0..4; tail is reverse.
        actions = [r["action"] for r in records]
        self.assertEqual(actions, ["action_4", "action_3", "action_2", "action_1", "action_0"])

    def test_read_tail_caps_at_n(self):
        for i in range(20):
            audit.emit(action=f"a{i}", ip="x")
        self.assertEqual(len(audit.read_tail(n=3)), 3)
        self.assertEqual(len(audit.read_tail(n=100)), 20)

    def test_read_tail_empty_file_returns_empty_list(self):
        self.assertEqual(audit.read_tail(n=10), [])

    def test_read_tail_filters_by_category(self):
        audit.emit(category="admin", action="a1")
        audit.emit(category="mail", action="m1")
        audit.emit(category="admin", action="a2")
        admin_only = audit.read_tail(n=10, category="admin")
        mail_only = audit.read_tail(n=10, category="mail")
        self.assertEqual([r["action"] for r in admin_only], ["a2", "a1"])
        self.assertEqual([r["action"] for r in mail_only], ["m1"])

    def test_read_tail_skips_corrupt_lines(self):
        """A truncated last line (e.g. crash mid-write) shouldn't break
        the whole panel. Mix valid + bogus lines and confirm the valid
        ones still come back."""
        audit.emit(action="ok_one", ip="x")
        # Append a bogus line directly.
        with (self.tmp / "admin_audit.jsonl").open("a") as f:
            f.write("not-json garbage\n")
        audit.emit(action="ok_two", ip="x")
        records = audit.read_tail(n=10)
        self.assertEqual([r["action"] for r in records], ["ok_two", "ok_one"])

    # ------------------------------------------------------------------
    # Rotation
    # ------------------------------------------------------------------
    def test_rotation_moves_to_jsonl_1(self):
        """When the file exceeds the soft-cap on the next write, it
        gets renamed to .jsonl.1 and the next emit starts fresh."""
        # Force-write a >5 MB file by emitting one big line.
        audit.emit(action="seed")
        log_path = self.tmp / "admin_audit.jsonl"
        with log_path.open("a") as f:
            f.write("x" * (6 * 1024 * 1024) + "\n")
        # Next emit should trigger rotation.
        audit.emit(action="post_rotation", ip="2.2.2.2")
        # Old file should now exist as .jsonl.1 and the new file should
        # contain only the post-rotation entry.
        self.assertTrue((self.tmp / "admin_audit.jsonl.1").exists())
        new_lines = log_path.read_text().splitlines()
        self.assertEqual(len(new_lines), 1)
        self.assertEqual(json.loads(new_lines[0])["action"], "post_rotation")

    # ------------------------------------------------------------------
    # GDPR data minimisation (Art. 5(1)(c)) + storage limitation (5(1)(e))
    # ------------------------------------------------------------------
    def test_ipv4_anonymized_to_slash_24(self):
        """User IPv4 must hit disk with the last octet zeroed — no raw
        IPs in audit logs under GDPR."""
        audit.emit(action="login_ok", ip="192.168.65.7")
        rec = audit.read_tail(n=1)[0]
        self.assertEqual(rec["ip"], "192.168.65.0")

    def test_ipv6_anonymized_to_slash_64(self):
        """IPv6 host portion (last 64 bits) zeroed, network portion kept
        so geo / ASN can still be derived for ops if needed."""
        audit.emit(action="login_ok", ip="2001:db8:1234:5678:dead:beef:cafe:f00d")
        rec = audit.read_tail(n=1)[0]
        self.assertEqual(rec["ip"], "2001:db8:1234:5678::")

    def test_unparseable_ip_passes_through_unchanged(self):
        """``unknown`` / proxy-mangled garbage / None: we keep the row,
        we just can't anonymise what we can't parse. This is by design
        — silently swallowing bad input would hide upstream bugs."""
        audit.emit(action="login_ok", ip="unknown")
        audit.emit(action="login_ok", ip=None)
        records = audit.read_tail(n=10)
        ips = [r["ip"] for r in records]
        self.assertIn("unknown", ips)
        self.assertIn(None, ips)

    def test_read_tail_filters_records_older_than_retention(self):
        """30-day cutoff: an audit row written by hand with an old
        timestamp must not appear in read_tail output. Older records
        are still on disk (size rotation drops them naturally) but
        invisible to readers."""
        log_path = self.tmp / "admin_audit.jsonl"
        # Hand-craft an "ancient" record (90 days old) + a fresh one.
        from datetime import datetime, timedelta, timezone
        ancient_ts = (datetime.now(tz=timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            json.dumps({"ts": ancient_ts, "category": "admin", "action": "ancient",
                        "ok": True, "ip": None, "target": None, "detail": None}) + "\n"
        )
        # Now emit a fresh one through the helper.
        audit.emit(action="recent", ip="1.1.1.1")
        actions = [r["action"] for r in audit.read_tail(n=10)]
        self.assertEqual(actions, ["recent"])
        self.assertNotIn("ancient", actions)


if __name__ == "__main__":
    unittest.main()
