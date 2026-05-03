#!/usr/bin/env python3
"""Unit tests for apps/pmet_backend/worker/watchdog.py

Regression cover for the liveness watchdog (problem 2 in TODO.md). The
watchdog scans tasks/*.json for status==running tasks whose
progress.json has gone stale beyond LIVENESS_TIMEOUT_SEC, marks them
failed, and (in production) kills the bash process tree.

These tests stub out config + the kill function so they run anywhere
without docker, and exercise the staleness decision logic across the
edge cases that matter:

  - actively-progressing task → not killed
  - stale progress.json beyond threshold → killed, JSON marked failed
  - running task with no progress.json yet but old started_at → killed
  - non-running tasks (completed / failed / cancelled) → ignored
  - malformed JSON → ignored
  - missing started_at and missing progress.json → ignored

Run via tests/unit/run.sh, which invokes:
  python3 tests/unit/test_watchdog_staleness.py
Exits non-zero on any assertion failure.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "apps"))

# Importing the watchdog also imports config, which mkdir's RESULT_DIR.
# That's fine: it operates on the real repo (host) results/ which is
# already present. The tests then point watchdog at a tmp dir via the
# config patch in setUp.
from pmet_backend.worker import watchdog as wd  # noqa: E402


class WatchdogStalenessTests(unittest.TestCase):
    def setUp(self):
        # Per-test scratch root; mock config to point at it.
        self.tmp = Path(tempfile.mkdtemp(prefix="pmet_wd_test_"))
        self.tasks_dir = self.tmp / "tasks"
        self.results_root = self.tmp
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

        self.cfg_patch = patch.multiple(
            wd.config,
            TASKS_DIR=self.tasks_dir,
            RESULT_DIR=self.results_root,
        )
        self.cfg_patch.start()

        # Stub the kill function — we just want to confirm it was called
        # with the right PID, never actually signal a real process.
        self.killed = []
        self.kill_patch = patch.object(
            wd, "kill_process_tree", side_effect=lambda pid: self.killed.append(pid) or [pid]
        )
        self.kill_patch.start()

    def tearDown(self):
        self.cfg_patch.stop()
        self.kill_patch.stop()
        # Best-effort cleanup; tmp is per-test so leak doesn't bleed.
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _write_task(self, task_id: str, status: str = "running",
                    started_at: str | None = None) -> Path:
        meta = {"task_id": task_id, "status": status}
        if started_at:
            meta["started_at"] = started_at
        path = self.tasks_dir / f"{task_id}.json"
        path.write_text(json.dumps(meta, indent=2))
        # Also create the per-task results dir.
        (self.results_root / task_id).mkdir(parents=True, exist_ok=True)
        return path

    def _write_progress(self, task_id: str, age_sec: float) -> None:
        p = self.results_root / task_id / "progress.json"
        p.write_text('{"stage": "x", "stage_index": 1, "total_stages": 2}')
        old_mtime = time.time() - age_sec
        os.utime(p, (old_mtime, old_mtime))

    def _write_pid(self, task_id: str, pid: int) -> None:
        (self.results_root / task_id / "worker.pid").write_text(str(pid))

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------
    def test_fresh_task_is_not_killed(self):
        """progress.json updated 5 s ago, threshold 60 s → leave alone."""
        self._write_task("t_fresh")
        self._write_progress("t_fresh", age_sec=5)
        self._write_pid("t_fresh", pid=99999)

        reason = wd._kill_if_stale(self.tasks_dir / "t_fresh.json", threshold_sec=60)
        self.assertIsNone(reason)
        self.assertEqual(self.killed, [])

        meta = json.loads((self.tasks_dir / "t_fresh.json").read_text())
        self.assertEqual(meta["status"], "running")

    def test_stale_progress_is_killed(self):
        """progress.json 600 s old, threshold 60 s → kill + mark failed."""
        self._write_task("t_stale")
        self._write_progress("t_stale", age_sec=600)
        self._write_pid("t_stale", pid=12345)

        reason = wd._kill_if_stale(self.tasks_dir / "t_stale.json", threshold_sec=60)
        self.assertIsNotNone(reason)
        self.assertIn("liveness probe", reason)
        self.assertIn("threshold 60s", reason)
        self.assertEqual(self.killed, [12345])

        meta = json.loads((self.tasks_dir / "t_stale.json").read_text())
        self.assertEqual(meta["status"], "failed")
        self.assertIn("liveness probe", meta["error_message"])
        self.assertIn("completed_at", meta)

    def test_no_progress_file_falls_back_to_started_at(self):
        """Pipeline never reached first emit_progress; check started_at."""
        old_started = (datetime.utcnow() - timedelta(seconds=600)).isoformat()
        self._write_task("t_wedged", started_at=old_started)
        self._write_pid("t_wedged", pid=22222)
        # Note: no progress.json written

        reason = wd._kill_if_stale(self.tasks_dir / "t_wedged.json", threshold_sec=60)
        self.assertIsNotNone(reason)
        self.assertEqual(self.killed, [22222])

    def test_completed_task_is_ignored(self):
        """status != running → never touched, even with stale progress."""
        self._write_task("t_done", status="completed")
        self._write_progress("t_done", age_sec=10000)

        reason = wd._kill_if_stale(self.tasks_dir / "t_done.json", threshold_sec=60)
        self.assertIsNone(reason)
        self.assertEqual(self.killed, [])

    def test_cancelled_task_is_ignored(self):
        self._write_task("t_cancel", status="cancelled")
        self._write_progress("t_cancel", age_sec=10000)

        reason = wd._kill_if_stale(self.tasks_dir / "t_cancel.json", threshold_sec=60)
        self.assertIsNone(reason)
        self.assertEqual(self.killed, [])

    def test_malformed_json_is_ignored(self):
        path = self.tasks_dir / "t_bad.json"
        path.write_text("{ not valid json")
        reason = wd._kill_if_stale(path, threshold_sec=60)
        self.assertIsNone(reason)

    def test_missing_progress_and_no_started_at_is_ignored(self):
        """Without either signal we cannot judge staleness; do nothing."""
        self._write_task("t_unknown", started_at=None)
        # No progress.json, no started_at field beyond what _write_task
        # writes (it omits started_at when arg is None).
        reason = wd._kill_if_stale(self.tasks_dir / "t_unknown.json", threshold_sec=60)
        self.assertIsNone(reason)

    def test_threshold_boundary(self):
        """Age below threshold → keep; at/above threshold → kill."""
        self._write_task("t_below")
        self._write_progress("t_below", age_sec=59)
        self.assertIsNone(wd._kill_if_stale(self.tasks_dir / "t_below.json", 60))

        self._write_task("t_above")
        self._write_progress("t_above", age_sec=61)
        self.assertIsNotNone(wd._kill_if_stale(self.tasks_dir / "t_above.json", 60))

    def test_kill_handles_missing_pid_file(self):
        """Stale task without a worker.pid file → still mark failed,
        skip the kill silently. Mirrors a worker that never wrote PID."""
        self._write_task("t_nopid")
        self._write_progress("t_nopid", age_sec=600)
        # No worker.pid file written

        reason = wd._kill_if_stale(self.tasks_dir / "t_nopid.json", threshold_sec=60)
        self.assertIsNotNone(reason)
        self.assertEqual(self.killed, [])  # kill_process_tree never invoked

        meta = json.loads((self.tasks_dir / "t_nopid.json").read_text())
        self.assertEqual(meta["status"], "failed")


if __name__ == "__main__":
    # Run unittest with a verbose printer that mirrors the R test format.
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(WatchdogStalenessTests)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
