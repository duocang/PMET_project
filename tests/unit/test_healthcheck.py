#!/usr/bin/env python3
"""Unit tests for services/healthcheck.py — admin self-test probes.

A6 in the admin backlog. Five probes:

  - smtp           (connect + STARTTLS + AUTH; no mail sent)
  - redis          (raw TCP PING)
  - disk           (shutil.disk_usage on RESULT_DIR)
  - tasks_dir      (atomic-temp-file write/delete)
  - configure_dir  (operator-supplied files present?)

Each test stubs the external dependency so the suite stays
hermetic — no real SMTP server, no live redis. The point is to pin
the status thresholds and the shape of the response.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from collections import namedtuple
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "apps"))

from pmet_backend.config import config  # noqa: E402
from pmet_backend.services import healthcheck  # noqa: E402


_FakeDiskUsage = namedtuple("_FakeDiskUsage", "total used free")


class DiskProbeTests(unittest.TestCase):
    def test_disk_ok_when_free_above_5gb(self):
        with patch.object(healthcheck.shutil, "disk_usage",
                          return_value=_FakeDiskUsage(total=100 * 2**30,
                                                     used=20 * 2**30,
                                                     free=80 * 2**30)):
            status, detail = healthcheck._disk()
        self.assertEqual(status, "ok")
        self.assertEqual(detail["free_gb"], 80.0)
        self.assertGreater(detail["total_gb"], 0)

    def test_disk_warn_when_free_below_5gb(self):
        with patch.object(healthcheck.shutil, "disk_usage",
                          return_value=_FakeDiskUsage(total=100 * 2**30,
                                                     used=98 * 2**30,
                                                     free=2 * 2**30)):
            status, _ = healthcheck._disk()
        self.assertEqual(status, "warn")

    def test_disk_fail_when_free_below_1gb(self):
        with patch.object(healthcheck.shutil, "disk_usage",
                          return_value=_FakeDiskUsage(total=100 * 2**30,
                                                     used=99.5 * 2**30,
                                                     free=0.5 * 2**30)):
            status, _ = healthcheck._disk()
        self.assertEqual(status, "fail")

    def test_disk_fail_captures_exception(self):
        with patch.object(healthcheck.shutil, "disk_usage", side_effect=OSError("no permission")):
            status, detail = healthcheck._disk()
        self.assertEqual(status, "fail")
        self.assertIn("error", detail)


class TasksDirProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pmet_health_test_"))
        self.cfg_patch = patch.object(config, "TASKS_DIR", self.tmp / "tasks")
        self.cfg_patch.start()

    def tearDown(self):
        self.cfg_patch.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_tasks_dir_ok_when_writable(self):
        status, detail = healthcheck._tasks_dir_writable()
        self.assertEqual(status, "ok")
        # The probe creates + deletes a temp file — afterwards the
        # directory itself should still exist (created lazily) and be
        # empty.
        self.assertTrue(Path(detail["path"]).is_dir())

    def test_tasks_dir_fail_when_path_is_a_file(self):
        # Replace TASKS_DIR with an actual file — mkdir(exist_ok=True)
        # will raise FileExistsError on this.
        bad = self.tmp / "blocked"
        bad.write_text("i am a file")
        with patch.object(config, "TASKS_DIR", bad):
            status, detail = healthcheck._tasks_dir_writable()
        self.assertEqual(status, "fail")
        self.assertIn("error", detail)


class ConfigureDirProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pmet_health_cfg_"))
        self.cfg_patch = patch.object(config, "CONFIGURE_DIR", self.tmp)
        self.cfg_patch.start()

    def tearDown(self):
        self.cfg_patch.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_all_three_files_present_ok(self):
        for name in ("admin_token.txt", "email_credential.txt", "public_base_url.txt"):
            (self.tmp / name).write_text("x")
        status, detail = healthcheck._configure_dir()
        self.assertEqual(status, "ok")
        self.assertEqual(set(detail["present"]),
                         {"admin_token.txt", "email_credential.txt", "public_base_url.txt"})

    def test_missing_admin_token_is_fail(self):
        # Email + base_url present but no admin_token → admin features
        # disabled → loudest status, not just warn.
        (self.tmp / "email_credential.txt").write_text("x")
        (self.tmp / "public_base_url.txt").write_text("x")
        status, detail = healthcheck._configure_dir()
        self.assertEqual(status, "fail")
        self.assertIn("admin_token.txt", detail["missing"])

    def test_missing_optional_only_is_warn(self):
        # Token present, others missing → warn (degraded, not down).
        (self.tmp / "admin_token.txt").write_text("x")
        status, detail = healthcheck._configure_dir()
        self.assertEqual(status, "warn")
        self.assertIn("email_credential.txt", detail["missing"])


class RunAllTests(unittest.TestCase):
    def test_run_all_returns_five_checks_in_fixed_order(self):
        """Frontend rendering depends on the order so we don't shuffle
        the result across reloads."""
        # Patch every external dep to be cheap and successful.
        with patch.object(healthcheck, "_smtp", return_value=("warn", {"reason": "stub"})), \
             patch.object(healthcheck, "_redis", return_value=("ok", {"host": "x"})), \
             patch.object(healthcheck, "_disk", return_value=("ok", {"free_gb": 100})), \
             patch.object(healthcheck, "_tasks_dir_writable", return_value=("ok", {"path": "x"})), \
             patch.object(healthcheck, "_configure_dir", return_value=("ok", {})):
            out = healthcheck.run_all()
        names = [c["name"] for c in out["checks"]]
        self.assertEqual(names, ["smtp", "redis", "disk", "tasks_dir", "configure_dir"])


class SmtpProbeTests(unittest.TestCase):
    def test_smtp_warn_when_unconfigured(self):
        with patch.multiple(config, EMAIL_USERNAME="", EMAIL_PASSWORD="", EMAIL_SERVER=""):
            status, detail = healthcheck._smtp()
        self.assertEqual(status, "warn")
        self.assertIn("SMTP not configured", detail["reason"])


class RedisProbeTests(unittest.TestCase):
    def test_redis_parses_broker_url(self):
        """The probe extracts host:port from CELERY_BROKER_URL; without
        a real redis it should fail-fast with a network error, not
        crash on URL parsing."""
        import os
        with patch.dict(os.environ, {"CELERY_BROKER_URL": "redis://no-such-host.invalid:6379/0"}):
            status, detail = healthcheck._redis()
        # Status is 'fail' (connection refused / DNS failure), but the
        # parse step succeeded — detail has host + port populated.
        self.assertEqual(status, "fail")
        self.assertEqual(detail["host"], "no-such-host.invalid")
        self.assertEqual(detail["port"], 6379)


if __name__ == "__main__":
    unittest.main()
