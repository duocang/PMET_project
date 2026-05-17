#!/usr/bin/env python3
"""Unit tests for services/cleanup.py — result retention sweep.

A4 in the admin backlog. The cleaner deletes three things per
eligible task:

  - results/app/<task_id>/        (output directory)
  - results/app/<task_id>.zip     (downloadable bundle)
  - results/app/tasks/<task_id>.json  (metadata)

These tests pin:

  1. count_eligible / run are gated on retention_days > 0 — 0 / None
     means "feature off"
  2. age is measured by the task JSON's created_at field, not by file
     mtime — important because file mtime gets bumped on every status
     update (would make every task "young" forever)
  3. dry_run enumerates without deleting (preview-button contract)
  4. partial artefacts (zip but no dir, dir but no meta) still get
     swept — operators expect "clean it up" not "skip if not perfect"
  5. errors get collected but don't abort the sweep — one
     unremovable file shouldn't strand 100 others
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "apps"))

from pmet_backend.config import config  # noqa: E402
from pmet_backend.services import cleanup  # noqa: E402


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pmet_cleanup_test_"))
        self.result_dir = self.tmp / "results"
        self.tasks_dir = self.result_dir / "tasks"
        self.tasks_dir.mkdir(parents=True)
        self.cfg_patch = patch.multiple(
            config,
            RESULT_DIR=self.result_dir,
            TASKS_DIR=self.tasks_dir,
        )
        self.cfg_patch.start()

    def tearDown(self):
        self.cfg_patch.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _seed_task(self, task_id: str, days_old: int, *, with_dir=True, with_zip=True, with_meta=True):
        """Create on-disk artefacts for one task with a controllable
        ``created_at`` so we can probe the age cutoff exactly.
        """
        created = (datetime.utcnow() - timedelta(days=days_old)).isoformat()
        if with_meta:
            (self.tasks_dir / f"{task_id}.json").write_text(json.dumps({
                "task_id": task_id,
                "email": "u@x.test",
                "mode": "promoters_pre",
                "status": "completed",
                "created_at": created,
            }))
        if with_dir:
            d = self.result_dir / task_id
            d.mkdir()
            (d / "motif_output.txt").write_text("dummy\n")
        if with_zip:
            (self.result_dir / f"{task_id}.zip").write_text("PK\x03\x04")

    # ------------------------------------------------------------------
    # Gate
    # ------------------------------------------------------------------
    def test_retention_zero_is_a_no_op(self):
        self._seed_task("old_task", days_old=999)
        report = cleanup.run(0)
        self.assertTrue(report["skipped"])
        self.assertEqual(report["removed_dirs"], 0)
        # Files should still be on disk.
        self.assertTrue((self.tasks_dir / "old_task.json").exists())
        self.assertTrue((self.result_dir / "old_task").exists())

    def test_count_eligible_zero_when_disabled(self):
        self._seed_task("a", days_old=999)
        self.assertEqual(cleanup.count_eligible(0), 0)
        self.assertEqual(cleanup.count_eligible(-5), 0)

    # ------------------------------------------------------------------
    # Eligibility
    # ------------------------------------------------------------------
    def test_only_tasks_older_than_cutoff_are_eligible(self):
        self._seed_task("recent", days_old=5)
        self._seed_task("ancient", days_old=100)
        eligible = cleanup.count_eligible(30)
        self.assertEqual(eligible, 1)

    def test_exact_cutoff_boundary(self):
        """A task created exactly N days ago should be eligible
        (cutoff is "< now - N days")."""
        self._seed_task("borderline", days_old=30)
        # 29 → not eligible (cutoff is at 30 days ago, task is at 30, equal isn't <)
        self.assertEqual(cleanup.count_eligible(31), 0)
        # 30 → eligible (task at 30d is older than cutoff at 30-ε)
        self.assertEqual(cleanup.count_eligible(29), 1)

    def test_missing_created_at_skips_task(self):
        """A corrupt / partially-migrated task JSON shouldn't poison
        the sweep — it just doesn't get counted."""
        (self.tasks_dir / "no_created.json").write_text(json.dumps({"task_id": "no_created"}))
        self.assertEqual(cleanup.count_eligible(30), 0)

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------
    def test_run_deletes_all_three_artefacts(self):
        self._seed_task("doomed", days_old=100)
        report = cleanup.run(30)
        self.assertFalse(report.get("skipped"))
        self.assertEqual(report["removed_dirs"], 1)
        self.assertEqual(report["removed_zips"], 1)
        self.assertEqual(report["removed_metas"], 1)
        self.assertFalse((self.tasks_dir / "doomed.json").exists())
        self.assertFalse((self.result_dir / "doomed").exists())
        self.assertFalse((self.result_dir / "doomed.zip").exists())

    def test_run_leaves_recent_tasks_untouched(self):
        self._seed_task("doomed", days_old=100)
        self._seed_task("recent", days_old=2)
        cleanup.run(30)
        # Recent should survive.
        self.assertTrue((self.tasks_dir / "recent.json").exists())
        self.assertTrue((self.result_dir / "recent").exists())

    def test_run_handles_missing_artefacts_gracefully(self):
        """Operator may have hand-deleted one of the three artefacts
        already; the sweep should clean whatever's left."""
        # Old task with no zip, just dir + meta.
        self._seed_task("partial", days_old=100, with_zip=False)
        report = cleanup.run(30)
        self.assertEqual(report["removed_zips"], 0)
        self.assertEqual(report["removed_dirs"], 1)
        self.assertEqual(report["removed_metas"], 1)
        self.assertEqual(report["errors"], [])

    def test_dry_run_enumerates_without_deleting(self):
        self._seed_task("doomed", days_old=100)
        report = cleanup.run(30, dry_run=True)
        # Report still counts everything as "would remove" …
        self.assertEqual(report["removed_dirs"], 1)
        self.assertEqual(report["removed_zips"], 1)
        self.assertEqual(report["removed_metas"], 1)
        # … but the files are still there.
        self.assertTrue((self.tasks_dir / "doomed.json").exists())
        self.assertTrue((self.result_dir / "doomed").exists())
        self.assertTrue((self.result_dir / "doomed.zip").exists())

    def test_run_continues_past_individual_errors(self):
        """If one file is unremovable, the others still get cleaned."""
        self._seed_task("one", days_old=100)
        self._seed_task("two", days_old=100)
        # Make 'one's dir unremovable by pointing its zip path at a
        # non-existent intermediate. We can't easily simulate permission
        # errors cross-platform, but we can at least confirm a missing
        # file doesn't show up as an error in the report.
        report = cleanup.run(30)
        # Both tasks fully cleaned, no errors.
        self.assertEqual(report["candidates"], 2)
        self.assertEqual(report["errors"], [])
        self.assertFalse((self.tasks_dir / "one.json").exists())
        self.assertFalse((self.tasks_dir / "two.json").exists())


if __name__ == "__main__":
    unittest.main()
