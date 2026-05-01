#!/usr/bin/env python3
"""Unit tests for apps/pmet_backend/services/stage_status.py

Regression cover for the long-term Problem 4 fix in TODO.md
("task.status is a liar" — extending the binary status with a
filesystem-derived per-stage view).

Each test sets up a tmp dir mimicking results/app/<task_id>/, drops
the bare minimum artifacts to trigger one branch, and checks the
inferred stages list.

State machine:
  pending → running → completed | failed | cancelled
  per stage: pending | running | completed | failed | skipped

Run via tests/unit/run.sh.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "apps"))

from pmet_backend.services import stage_status as ss  # noqa: E402


class InferStagesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pmet_stages_test_"))
        self.task_dir = self.tmp / "pmet_test"
        self.task_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _write_indexing(self):
        d = self.task_dir / "indexing"
        d.mkdir(parents=True, exist_ok=True)
        (d / "universe.txt").write_text("AT1G00010\n")

    def _write_pairing(self, body: str = "motif1\tmotif2\tp_adj\nA\tB\t1e-9\n"):
        d = self.task_dir / "pairing"
        d.mkdir(parents=True, exist_ok=True)
        (d / "motif_output.txt").write_text(body)

    def _write_heatmap(self):
        plot = self.task_dir / "pairing" / "plot"
        plot.mkdir(parents=True, exist_ok=True)
        (plot / "heatmap.png").write_bytes(b"\x89PNG fake")

    def _write_zip(self):
        (self.tmp / f"{self.task_dir.name}.zip").write_bytes(b"PK fake")

    def _states(self, stages):
        return {s["name"]: s["state"] for s in stages}

    # ------------------------------------------------------------------
    # Happy path: full Promoters mode, every stage completed
    # ------------------------------------------------------------------
    def test_full_completed(self):
        self._write_indexing()
        self._write_pairing()
        self._write_heatmap()
        self._write_zip()
        meta = {"mode": "promoters", "status": "completed"}
        st = ss.infer_stages(meta, self.task_dir)
        self.assertEqual(self._states(st), {
            "indexing": "completed",
            "pairing":  "completed",
            "heatmap":  "completed",
            "zip":      "completed",
        })
        self.assertEqual(ss.derive_warnings(st), [])
        self.assertEqual(ss.derive_effective_status("completed", st), "completed")

    # ------------------------------------------------------------------
    # promoters_pre: indexing always shows as 'precomputed' (its own state,
    # distinct from 'skipped' which is reserved for warnings)
    # ------------------------------------------------------------------
    def test_promoters_pre_indexing_is_precomputed(self):
        self._write_indexing()  # mounted from precomputed
        self._write_pairing()
        self._write_heatmap()
        self._write_zip()
        meta = {"mode": "promoters_pre", "status": "completed"}
        st = ss.infer_stages(meta, self.task_dir)
        self.assertEqual(self._states(st), {
            "indexing": "precomputed",
            "pairing":  "completed",
            "heatmap":  "completed",
            "zip":      "completed",
        })
        # 'precomputed' is benign — must NOT generate a warning
        self.assertEqual(ss.derive_warnings(st), [])
        # And it should NOT flip the badge to completed_with_warnings
        self.assertEqual(ss.derive_effective_status("completed", st), "completed")

    # ------------------------------------------------------------------
    # The original Problem 4 case: pairing OK but heatmap crashed
    # ------------------------------------------------------------------
    def test_heatmap_failure_partial_result_path(self):
        self._write_pairing()
        # No heatmap, no zip
        meta = {"mode": "promoters_pre", "status": "failed",
                "error_message": "ggsave dim limit"}
        st = ss.infer_stages(meta, self.task_dir)
        self.assertEqual(self._states(st), {
            "indexing": "precomputed",  # promoters_pre always
            "pairing":  "completed",
            "heatmap":  "skipped",   # crashed but pairing data complete
            "zip":      "skipped",
        })
        warnings = ss.derive_warnings(st)
        self.assertTrue(any("heatmap" in w for w in warnings),
                        f"expected heatmap warning, got {warnings}")
        self.assertTrue(any("zip" in w for w in warnings),
                        f"expected zip warning, got {warnings}")

    # ------------------------------------------------------------------
    # Universe mismatch (cross-species): nothing produced beyond upload
    # ------------------------------------------------------------------
    def test_universe_mismatch_failure(self):
        # No indexing, no pairing, no heatmap, no zip
        meta = {"mode": "promoters_pre", "status": "failed",
                "error_message": "No genes match the index universe"}
        st = ss.infer_stages(meta, self.task_dir)
        # promoters_pre indexing → precomputed; pairing failed
        self.assertEqual(self._states(st), {
            "indexing": "precomputed",
            "pairing":  "failed",
            "heatmap":  "pending",
            "zip":      "pending",
        })

    # ------------------------------------------------------------------
    # Indexing-side failure (full Promoters mode)
    # ------------------------------------------------------------------
    def test_indexing_stage_failed(self):
        # Full mode, indexing dir empty / not produced, task failed
        meta = {"mode": "promoters", "status": "failed"}
        st = ss.infer_stages(meta, self.task_dir)
        self.assertEqual(self._states(st), {
            "indexing": "failed",
            "pairing":  "pending",   # never reached
            "heatmap":  "pending",
            "zip":      "pending",
        })

    # ------------------------------------------------------------------
    # Running mid-pipeline
    # ------------------------------------------------------------------
    def test_running_after_indexing(self):
        self._write_indexing()
        meta = {"mode": "promoters", "status": "running"}
        st = ss.infer_stages(meta, self.task_dir)
        self.assertEqual(self._states(st), {
            "indexing": "completed",
            "pairing":  "running",
            "heatmap":  "pending",
            "zip":      "pending",
        })

    def test_running_before_anything(self):
        meta = {"mode": "promoters", "status": "running"}
        st = ss.infer_stages(meta, self.task_dir)
        self.assertEqual(self._states(st), {
            "indexing": "running",
            "pairing":  "pending",
            "heatmap":  "pending",
            "zip":      "pending",
        })

    # ------------------------------------------------------------------
    # Cancelled task
    # ------------------------------------------------------------------
    def test_cancelled_mid_run(self):
        self._write_indexing()
        meta = {"mode": "promoters", "status": "cancelled"}
        st = ss.infer_stages(meta, self.task_dir)
        # Whatever was done is 'completed', the rest is 'skipped'
        self.assertEqual(self._states(st), {
            "indexing": "completed",
            "pairing":  "skipped",
            "heatmap":  "skipped",
            "zip":      "skipped",
        })

    # ------------------------------------------------------------------
    # derive_effective_status: completed_with_warnings vs completed
    # ------------------------------------------------------------------
    def test_completed_with_warnings_when_heatmap_skipped_with_note(self):
        # Hypothetical: status=completed but a stage carries a warning.
        # Constructed manually since infer_stages won't naturally
        # produce status=completed with heatmap skipped+note today,
        # but the function is still well-defined for that input.
        stages = [
            {"name": "indexing", "state": "precomputed", "note": "uses precomputed index"},
            {"name": "pairing",  "state": "completed"},
            {"name": "heatmap",  "state": "skipped", "note": "rendering skipped"},
            {"name": "zip",      "state": "completed"},
        ]
        self.assertEqual(ss.derive_effective_status("completed", stages),
                         "completed_with_warnings")

    def test_completed_clean_no_warnings(self):
        stages = [
            {"name": "indexing", "state": "precomputed", "note": "uses precomputed index"},
            {"name": "pairing",  "state": "completed"},
            {"name": "heatmap",  "state": "completed"},
            {"name": "zip",      "state": "completed"},
        ]
        self.assertEqual(ss.derive_effective_status("completed", stages),
                         "completed")

    def test_failed_pairing_failed_stays_failed(self):
        """When pairing itself failed, persisted=failed maps to failed
        (no usable output to advertise as 'partial')."""
        stages = [{"name": "pairing", "state": "failed"}]
        self.assertEqual(ss.derive_effective_status("failed", stages), "failed")

    def test_failed_with_pairing_ok_becomes_partial_success(self):
        """The matrix-run case: heatmap or zip crashed but pairing
        wrote motif_output.txt. Effective status flips from 'failed'
        to 'partial_success' so the badge reflects 'something went
        wrong but data is recoverable'."""
        stages = [
            {"name": "indexing", "state": "precomputed"},
            {"name": "pairing",  "state": "completed"},
            {"name": "heatmap",  "state": "skipped", "note": "rendering failed"},
            {"name": "zip",      "state": "skipped", "note": "late-stage"},
        ]
        self.assertEqual(ss.derive_effective_status("failed", stages),
                         "partial_success")

    def test_running_passes_through(self):
        stages = [{"name": "pairing", "state": "running"}]
        self.assertEqual(ss.derive_effective_status("running", stages), "running")


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(InferStagesTests)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
