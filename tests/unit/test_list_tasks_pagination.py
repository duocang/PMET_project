#!/usr/bin/env python3
"""Unit tests for the list endpoint /api/tasks — specifically that it
applies email / task_id filters BEFORE slicing into a page, not after.

The historical bug: list_tasks() did
    for f in sorted(...glob)[offset:offset+limit]:
        if email and ...: continue
which silently returned [] whenever the first `limit` newest task files
didn't match the user's email — even when matching tasks sat on disk
further down the list. The user-visible symptom was "I know I have
tasks under that email but the search returns nothing."

These tests pin the filter-first ordering by writing many newer
non-matching tasks and one older matching task, then asking for it via
both filter modes.
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "apps"))

from fastapi.testclient import TestClient  # noqa: E402

from pmet_backend.api.main import app  # noqa: E402
from pmet_backend.config import config  # noqa: E402


def _meta(task_id: str, email: str, mode: str = "promoters_pre", status: str = "completed") -> dict:
    return {
        "task_id": task_id,
        "email": email,
        "mode": mode,
        "status": status,
        "created_at": datetime.now().isoformat(),
        "started_at": datetime.now().isoformat(),
        "completed_at": datetime.now().isoformat(),
    }


class ListTasksPaginationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pmet_list_test_"))
        self.tasks_dir = self.tmp / "tasks"
        self.results_root = self.tmp
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.cfg_patch = patch.multiple(
            config,
            TASKS_DIR=self.tasks_dir,
            RESULT_DIR=self.results_root,
        )
        self.cfg_patch.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.cfg_patch.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.client.close()

    def _write_task(self, **overrides) -> str:
        m = _meta(**{
            "task_id": overrides.get("task_id", "pmet_test"),
            "email": overrides.get("email", "noone@example.com"),
            "mode": overrides.get("mode", "promoters_pre"),
            "status": overrides.get("status", "completed"),
        })
        m.update({k: v for k, v in overrides.items() if k in m})
        (self.tasks_dir / f"{m['task_id']}.json").write_text(json.dumps(m))
        return m["task_id"]

    # ------------------------------------------------------------------
    # Regression: filter-before-slice ordering
    # ------------------------------------------------------------------
    def test_email_filter_finds_match_buried_past_default_limit(self):
        """Write 60 tasks under one email + 1 newer-named-but-older
        target under another email. Default limit is 50. Buggy
        implementation slices 50 newest first → target slips through.
        Fixed implementation filters first → finds the 1 match.

        Newest-first sort is by reverse filename, so an alphabetically
        LATER task_id beats an alphabetically earlier one (no FS mtime
        dependency). We name the noise tasks with the highest letters
        to make sure they sort newest.
        """
        for i in range(60):
            self._write_task(
                task_id=f"pmet_zzz{i:02d}",       # sorts newest
                email="other@example.com",
            )
        self._write_task(
            task_id="pmet_aaa00",                  # sorts oldest
            email="target@example.com",
        )

        r = self.client.get("/api/tasks?email=target@example.com")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        ids = [t["task_id"] for t in body["tasks"]]
        self.assertEqual(ids, ["pmet_aaa00"],
                         "target task buried past default limit must still be returned")
        self.assertEqual(body["total"], 1)

    def test_task_id_filter_finds_match_buried_past_default_limit(self):
        """Same shape but with the task_id substring filter."""
        for i in range(60):
            self._write_task(task_id=f"pmet_zzz{i:02d}", email="x@y.com")
        self._write_task(task_id="pmet_aaa_findme", email="x@y.com")

        r = self.client.get("/api/tasks?task_id=findme")
        body = r.json()
        ids = [t["task_id"] for t in body["tasks"]]
        self.assertEqual(ids, ["pmet_aaa_findme"])
        self.assertEqual(body["total"], 1)

    def test_total_reflects_match_count_not_page_size(self):
        """`total` is the count after filtering (the field's natural
        meaning) — useful for the frontend to decide whether to paginate.
        Limit caps the page; total still reports all matches."""
        for i in range(15):
            self._write_task(task_id=f"pmet_target{i:02d}", email="me@x.com")

        r = self.client.get("/api/tasks?email=me@x.com&limit=5")
        body = r.json()
        self.assertEqual(len(body["tasks"]), 5)
        self.assertEqual(body["total"], 15)

    def test_limit_and_offset_paginate_within_filtered_results(self):
        """Page 2 with limit=5 should give matches 6..10 of the filtered
        set, regardless of how many other-email files sit in between
        on disk."""
        # Sprinkle noise tasks among the targets (alphabetically
        # interleaved) so a buggy implementation that slices first would
        # not just skip past the noise but also drop matching pages.
        for i in range(10):
            self._write_task(task_id=f"pmet_a_target_{i:02d}", email="me@x.com")
        for i in range(10):
            self._write_task(task_id=f"pmet_b_noise_{i:02d}", email="other@x.com")

        r = self.client.get("/api/tasks?email=me@x.com&limit=5&offset=0")
        page1 = [t["task_id"] for t in r.json()["tasks"]]
        self.assertEqual(len(page1), 5)

        r = self.client.get("/api/tasks?email=me@x.com&limit=5&offset=5")
        page2 = [t["task_id"] for t in r.json()["tasks"]]
        self.assertEqual(len(page2), 5)

        # No overlap between pages, and together they cover all 10 matches.
        self.assertEqual(set(page1) | set(page2),
                         {f"pmet_a_target_{i:02d}" for i in range(10)})
        self.assertEqual(set(page1) & set(page2), set())

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------
    def test_empty_tasks_dir_returns_empty_list(self):
        r = self.client.get("/api/tasks")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["tasks"], [])
        self.assertEqual(body["total"], 0)

    def test_malformed_json_file_is_skipped_not_crashing(self):
        """A junk *.json in TASKS_DIR shouldn't take down the whole
        endpoint. A bad write or interrupted save left a corrupt file
        once and the list 500'd — defensive json.loads guard prevents
        the regression."""
        self._write_task(task_id="pmet_good", email="x@y.com")
        (self.tasks_dir / "pmet_corrupt.json").write_text("{not valid json")

        r = self.client.get("/api/tasks")
        self.assertEqual(r.status_code, 200)
        ids = [t["task_id"] for t in r.json()["tasks"]]
        self.assertIn("pmet_good", ids)
        self.assertNotIn("pmet_corrupt", ids)

    def test_no_filter_returns_all_within_limit(self):
        for i in range(10):
            self._write_task(task_id=f"pmet_t{i:02d}", email="x@y.com")
        r = self.client.get("/api/tasks?limit=20")
        self.assertEqual(len(r.json()["tasks"]), 10)
        self.assertEqual(r.json()["total"], 10)


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(ListTasksPaginationTests)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
