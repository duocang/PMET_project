#!/usr/bin/env python3
"""Unit tests for the partial-result rescue path on /api/tasks/{id}.

Regression cover for "Problem 4 — task.status is a liar" (TODO.md). The
PMET pipeline writes pairing/motif_output.txt before running the R
heatmap and the zip stage. Either of those late stages can fail, which
flips status to `failed` even though the scientific payload is on disk.
The rescue path: GET /tasks/{id} returns a partial_result_link when
status==failed AND motif_output.txt exists, pointing at
GET /tasks/{id}/partial-result which streams the TSV directly.

These tests stub config to a tmp dir and exercise the helper +
endpoint logic without docker / celery / a real worker. The fastapi
TestClient handles the HTTP shape (status code, header, payload).

Run via tests/unit/run.sh; exits non-zero on any assertion failure.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "apps"))

from fastapi.testclient import TestClient  # noqa: E402

from pmet_backend.api.routes import tasks as tasks_route  # noqa: E402
from pmet_backend.api.main import app  # noqa: E402
from pmet_backend.config import config  # noqa: E402


SAMPLE_TASK_META = {
    "task_id": "pmet_partialtest1",
    "email": "test@local",
    "mode": "promoters_pre",
    "status": "failed",
    "error_message": "heatmap step failed",
    "created_at": "2026-05-01T10:00:00",
    "started_at": "2026-05-01T10:00:01",
    "completed_at": "2026-05-01T10:05:00",
}


class PartialResultLinkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pmet_partial_test_"))
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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _write_task(self, **overrides) -> str:
        meta = {**SAMPLE_TASK_META, **overrides}
        task_id = meta["task_id"]
        (self.tasks_dir / f"{task_id}.json").write_text(json.dumps(meta))
        (self.results_root / task_id).mkdir(parents=True, exist_ok=True)
        return task_id

    def _write_motif_output(self, task_id: str, body: str = "motif1\tmotif2\tp_adj\nA\tB\t0.001\n"):
        pairing = self.results_root / task_id / "pairing"
        pairing.mkdir(parents=True, exist_ok=True)
        (pairing / "motif_output.txt").write_text(body)

    # ------------------------------------------------------------------
    # _locate_motif_output helper
    # ------------------------------------------------------------------
    def test_locate_returns_path_when_file_exists_and_nonempty(self):
        tid = self._write_task()
        self._write_motif_output(tid)
        path = tasks_route._locate_motif_output(tid)
        self.assertIsNotNone(path)
        self.assertTrue(path.is_file())

    def test_locate_returns_none_when_file_missing(self):
        tid = self._write_task()
        self.assertIsNone(tasks_route._locate_motif_output(tid))

    def test_locate_returns_none_when_file_empty(self):
        """An empty file is treated the same as missing — the pairing
        stage clearly didn't write anything useful, no point dangling
        a download link."""
        tid = self._write_task()
        pairing = self.results_root / tid / "pairing"
        pairing.mkdir(parents=True, exist_ok=True)
        (pairing / "motif_output.txt").write_text("")
        self.assertIsNone(tasks_route._locate_motif_output(tid))

    # ------------------------------------------------------------------
    # GET /tasks/{id} surfaces partial_result_link iff failed + file
    # ------------------------------------------------------------------
    def test_failed_with_motif_output_surfaces_partial_link(self):
        tid = self._write_task(status="failed")
        body_text = "motif1\tmotif2\tp_adj\nA\tB\t0.001\n"
        self._write_motif_output(tid, body_text)
        r = self.client.get(f"/api/tasks/{tid}")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "failed")
        self.assertEqual(body["partial_result_link"], f"/api/tasks/{tid}/partial-result")
        # Size byte count must accompany the link so the UI can show
        # "Download partial result (~993 MB)" before the user clicks.
        self.assertEqual(body["partial_result_size_bytes"], len(body_text.encode()))

    def test_failed_without_motif_output_no_partial_link(self):
        tid = self._write_task(status="failed")
        r = self.client.get(f"/api/tasks/{tid}")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "failed")
        self.assertIsNone(body["partial_result_link"])
        self.assertIsNone(body["partial_result_size_bytes"])

    def test_completed_task_no_partial_link(self):
        """Completed tasks already have result_link; partial is just
        for the failure-rescue case."""
        tid = self._write_task(status="completed")
        self._write_motif_output(tid)
        r = self.client.get(f"/api/tasks/{tid}")
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json()["partial_result_link"])
        self.assertIsNone(r.json()["partial_result_size_bytes"])

    def test_completed_task_with_zip_returns_result_size(self):
        """When the result zip is on disk, result_size_bytes is populated
        so the success-download button can render '(123 MB)'."""
        tid = self._write_task(status="completed")
        zip_body = b"fake zip content"
        (self.results_root / f"{tid}.zip").write_bytes(zip_body)
        r = self.client.get(f"/api/tasks/{tid}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["result_size_bytes"], len(zip_body))

    def test_completed_task_without_zip_no_result_size(self):
        """No zip yet (e.g. running, or zip cleaned up) → no size."""
        tid = self._write_task(status="completed")
        r = self.client.get(f"/api/tasks/{tid}")
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json()["result_size_bytes"])

    def test_running_task_no_partial_link(self):
        tid = self._write_task(status="running")
        self._write_motif_output(tid)
        r = self.client.get(f"/api/tasks/{tid}")
        self.assertIsNone(r.json()["partial_result_link"])
        self.assertIsNone(r.json()["partial_result_size_bytes"])

    # ------------------------------------------------------------------
    # GET /tasks/{id}/partial-result downloads the file
    # ------------------------------------------------------------------
    def test_partial_result_download_returns_motif_output(self):
        tid = self._write_task(status="failed")
        body = "motif1\tmotif2\tp_adj\nA\tB\t1e-9\n"
        self._write_motif_output(tid, body)
        r = self.client.get(f"/api/tasks/{tid}/partial-result")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.text, body)
        # Should set a sensible filename in Content-Disposition
        cd = r.headers.get("content-disposition", "")
        self.assertIn(f"{tid}_motif_output.txt", cd)
        # X-Accel-Buffering: no — tells nginx to stream chunks straight
        # through instead of buffering the whole (potentially GB-scale)
        # response before forwarding.
        self.assertEqual(r.headers.get("x-accel-buffering"), "no")

    def test_partial_result_404_when_file_missing(self):
        tid = self._write_task(status="failed")
        # No motif_output.txt written
        r = self.client.get(f"/api/tasks/{tid}/partial-result")
        self.assertEqual(r.status_code, 404)

    def test_partial_result_404_when_task_unknown(self):
        r = self.client.get("/api/tasks/pmet_does_not_exist/partial-result")
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(PartialResultLinkTests)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
