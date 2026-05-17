#!/usr/bin/env python3
"""Unit tests for api/routes/admin_tasks.py — admin-only per-task ops.

Three endpoints:

  GET  /api/admin/task/<id>/debug   — meta dump + stderr tail
  PUT  /api/admin/task/<id>/note    — set / clear admin-authored note
  POST /api/admin/task/<id>/rerun   — duplicate task and queue rerun

All three are require_admin-gated. The tests below set an admin cookie
via the canonical login flow first (so the auth code path is also
exercised), then probe each endpoint.

The celery `.delay()` call inside rerun is stubbed out — we test that
the metadata is correctly cloned, not the celery transport.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "apps"))

from fastapi.testclient import TestClient  # noqa: E402

from pmet_backend.api.main import app  # noqa: E402
from pmet_backend.config import config  # noqa: E402
from pmet_backend.api.routes import admin as admin_mod  # noqa: E402


ADMIN_TOKEN_FIXTURE = "test-admin-token-do-not-use-in-prod"


class AdminTasksBase(unittest.TestCase):
    """Shared setup: tmp dirs + ADMIN_TOKEN + logged-in TestClient."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pmet_admintasks_test_"))
        self.tasks_dir = self.tmp / "results" / "tasks"
        self.result_dir = self.tmp / "results"
        self.tasks_dir.mkdir(parents=True)
        self.configure_dir = self.tmp / "configure"
        self.configure_dir.mkdir()
        self.project_root = self.tmp / "repo"
        (self.project_root / "results").mkdir(parents=True)
        # Mirror RESULT_DIR under PROJECT_ROOT/results so rerun's
        # upload-path existence check resolves correctly.
        (self.project_root / "results").rmdir()
        (self.project_root / "results").symlink_to(self.result_dir)

        self.cfg_patch = patch.multiple(
            config,
            RESULT_DIR=self.result_dir,
            TASKS_DIR=self.tasks_dir,
            CONFIGURE_DIR=self.configure_dir,
            PROJECT_ROOT=self.project_root,
            ADMIN_TOKEN=ADMIN_TOKEN_FIXTURE,
        )
        self.cfg_patch.start()
        # Clear the in-process brute-force counters between cases —
        # other tests in this run may have triggered them.
        admin_mod._reset_login_state_for_tests()

        self.client = TestClient(app)
        # Log in once so the client picks up the admin cookie.
        r = self.client.post("/api/admin/login", json={"token": ADMIN_TOKEN_FIXTURE})
        self.assertEqual(r.status_code, 200, r.text)

    def tearDown(self):
        self.cfg_patch.stop()
        admin_mod._reset_login_state_for_tests()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.client.close()

    def _write_task(self, task_id: str, **overrides) -> Path:
        meta = {
            "task_id": task_id,
            "email": "u@x.test",
            "mode": "promoters_pre",
            "status": "failed",
            "created_at": datetime.utcnow().isoformat(),
            "genes_file": None,
            "fasta_file": None,
            "gff3_file": None,
            "meme_file": None,
            "premade_index": "data/precomputed_indexes/Arabidopsis_thaliana/CIS-BP2",
        }
        meta.update(overrides)
        path = self.tasks_dir / f"{task_id}.json"
        path.write_text(json.dumps(meta))
        return path


# ----------------------------------------------------------------------
# GET /api/admin/task/<id>/debug
# ----------------------------------------------------------------------
class DebugEndpointTests(AdminTasksBase):
    def test_debug_returns_meta_and_no_stderr_when_log_absent(self):
        self._write_task("phaseX_abc")
        r = self.client.get("/api/admin/task/phaseX_abc/debug")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["task_id"], "phaseX_abc")
        self.assertEqual(body["meta"]["status"], "failed")
        self.assertIsNone(body["stderr_tail"])

    def test_debug_tails_last_50_lines_of_stderr_log(self):
        self._write_task("phaseX_abc")
        log_dir = self.result_dir / "phaseX_abc"
        log_dir.mkdir()
        # 60 lines → expect only the last 50 back.
        (log_dir / "stderr.log").write_text("\n".join(f"line {i}" for i in range(60)))
        r = self.client.get("/api/admin/task/phaseX_abc/debug")
        self.assertEqual(r.status_code, 200)
        tail = r.json()["stderr_tail"]
        self.assertEqual(len(tail), 50)
        self.assertEqual(tail[0], "line 10")
        self.assertEqual(tail[-1], "line 59")

    def test_debug_404_on_unknown_task(self):
        r = self.client.get("/api/admin/task/no_such_task/debug")
        self.assertEqual(r.status_code, 404)

    def test_debug_requires_admin(self):
        self._write_task("phaseX_abc")
        # New client without cookie.
        with TestClient(app) as anon:
            r = anon.get("/api/admin/task/phaseX_abc/debug")
        # 401 (not admin) — NOT 503 (which would mean admin disabled).
        self.assertEqual(r.status_code, 401)


# ----------------------------------------------------------------------
# PUT /api/admin/task/<id>/note
# ----------------------------------------------------------------------
class NoteEndpointTests(AdminTasksBase):
    def test_note_set_persists_in_task_json(self):
        path = self._write_task("phaseX_abc")
        r = self.client.put("/api/admin/task/phaseX_abc/note", json={"note": "  service down 5 min  "})
        self.assertEqual(r.status_code, 200, r.text)
        meta = json.loads(path.read_text())
        # Stripped, not truncated since under cap.
        self.assertEqual(meta["admin_note"], "service down 5 min")
        self.assertEqual(r.json()["admin_note"], "service down 5 min")

    def test_note_empty_clears_field(self):
        path = self._write_task("phaseX_abc", admin_note="old text")
        r = self.client.put("/api/admin/task/phaseX_abc/note", json={"note": ""})
        self.assertEqual(r.status_code, 200)
        meta = json.loads(path.read_text())
        self.assertNotIn("admin_note", meta)
        self.assertIsNone(r.json()["admin_note"])

    def test_note_truncated_at_1000_chars(self):
        path = self._write_task("phaseX_abc")
        long_note = "A" * 5000
        self.client.put("/api/admin/task/phaseX_abc/note", json={"note": long_note})
        meta = json.loads(path.read_text())
        self.assertEqual(len(meta["admin_note"]), 1000)

    def test_note_requires_admin(self):
        self._write_task("phaseX_abc")
        with TestClient(app) as anon:
            r = anon.put("/api/admin/task/phaseX_abc/note", json={"note": "x"})
        self.assertEqual(r.status_code, 401)

    def test_note_404_on_unknown_task(self):
        r = self.client.put("/api/admin/task/no_such/note", json={"note": "x"})
        self.assertEqual(r.status_code, 404)


# ----------------------------------------------------------------------
# POST /api/admin/task/<id>/rerun
# ----------------------------------------------------------------------
class RerunEndpointTests(AdminTasksBase):
    def test_rerun_clones_meta_under_new_task_id(self):
        self._write_task("phaseX_abc", ic_threshold=24, max_match=5)
        # run_pmet_task is a celery PromiseProxy and Task.delay is a
        # class-level method, so patch.object on the instance doesn't
        # stick. Replace the whole `run_pmet_task` symbol in the
        # worker.tasks.pmet module with a Mock — the route imports it
        # fresh each call so the swap is picked up.
        from unittest.mock import MagicMock
        import pmet_backend.worker.tasks.pmet as pmet_module
        fake_task = MagicMock()
        with patch.object(pmet_module, "run_pmet_task", fake_task):
            fake_delay = fake_task.delay
            r = self.client.post("/api/admin/task/phaseX_abc/rerun")
        self.assertEqual(r.status_code, 200, r.text)
        new_id = r.json()["task_id"]
        self.assertTrue(new_id.startswith("rerun_phaseX_abc_"))
        # Cloned metadata on disk.
        cloned = json.loads((self.tasks_dir / f"{new_id}.json").read_text())
        self.assertEqual(cloned["ic_threshold"], 24)
        self.assertEqual(cloned["max_match"], 5)
        self.assertEqual(cloned["status"], "pending")
        self.assertEqual(cloned["rerun_of"], "phaseX_abc")
        # Stale lifecycle fields stripped from the clone.
        self.assertNotIn("completed_at", cloned)
        self.assertNotIn("error_message", cloned)
        # Celery dispatched once.
        self.assertEqual(fake_delay.call_count, 1)

    def test_rerun_409_when_upload_file_missing(self):
        # Task references an upload that no longer exists on disk.
        self._write_task(
            "phaseX_abc",
            genes_file="results/phaseX_abc/upload/genes.txt",
            premade_index=None,
        )
        # run_pmet_task is a celery PromiseProxy and Task.delay is a
        # class-level method, so patch.object on the instance doesn't
        # stick. Replace the whole `run_pmet_task` symbol in the
        # worker.tasks.pmet module with a Mock — the route imports it
        # fresh each call so the swap is picked up.
        from unittest.mock import MagicMock
        import pmet_backend.worker.tasks.pmet as pmet_module
        fake_task = MagicMock()
        with patch.object(pmet_module, "run_pmet_task", fake_task):
            fake_delay = fake_task.delay
            r = self.client.post("/api/admin/task/phaseX_abc/rerun")
        self.assertEqual(r.status_code, 409, r.text)
        self.assertIn("no longer on disk", r.json()["detail"])
        fake_delay.assert_not_called()

    def test_rerun_404_on_unknown_task(self):
        r = self.client.post("/api/admin/task/no_such/rerun")
        self.assertEqual(r.status_code, 404)

    def test_rerun_requires_admin(self):
        self._write_task("phaseX_abc")
        with TestClient(app) as anon:
            r = anon.post("/api/admin/task/phaseX_abc/rerun")
        self.assertEqual(r.status_code, 401)

    def test_rerun_rolls_back_meta_when_celery_queue_fails(self):
        self._write_task("phaseX_abc")
        from unittest.mock import MagicMock
        import pmet_backend.worker.tasks.pmet as pmet_module
        fake_task = MagicMock()
        fake_task.delay.side_effect = RuntimeError("redis unreachable")
        with patch.object(pmet_module, "run_pmet_task", fake_task):
            r = self.client.post("/api/admin/task/phaseX_abc/rerun")
        self.assertEqual(r.status_code, 500)
        # The new task JSON should NOT linger after a queue failure —
        # otherwise the dashboard would show a phantom pending task.
        rerun_metas = list(self.tasks_dir.glob("rerun_*.json"))
        self.assertEqual(rerun_metas, [])


if __name__ == "__main__":
    unittest.main()
