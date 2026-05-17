#!/usr/bin/env python3
"""Unit tests for the admin stats aggregator
(apps/pmet_backend/api/routes/admin_stats.py).

We test the pure ``aggregate()`` function directly with stub task dicts
rather than spinning up the FS + TestClient + admin cookie dance. The
endpoint itself is a one-line wrapper that calls ``aggregate(_load_tasks(),
days)``, so logic regressions show up here.

The four behaviours we pin:

1. Out-of-window tasks are dropped before counting (the day window must
   be exclusive on the older side, otherwise a 30-day chart silently
   inherits ancient tasks).
2. Runtime samples only come from completed tasks, only when both
   started_at and completed_at exist, and only when the delta is
   positive (clock-skew tasks shouldn't poison the distribution).
3. Error messages are normalized — task-id-like hex tokens scrubbed —
   so multiple tasks failing identically collapse to one row instead
   of N rows each with count=1.
4. The trend is zero-filled across the whole window so the chart's
   x-axis is continuous even on quiet days.
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "apps"))

from pmet_backend.api.routes.admin_stats import (  # noqa: E402
    _normalize_error,
    _percentile,
    aggregate,
)


def _iso(dt: datetime) -> str:
    return dt.replace(tzinfo=None).isoformat()


def _task(
    task_id: str,
    *,
    status: str = "completed",
    mode: str = "promoters",
    created_at: datetime,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    error_message: str | None = None,
) -> dict:
    out = {
        "task_id": task_id,
        "email": "u@x.test",
        "mode": mode,
        "status": status,
        "created_at": _iso(created_at),
    }
    if started_at is not None:
        out["started_at"] = _iso(started_at)
    if completed_at is not None:
        out["completed_at"] = _iso(completed_at)
    if error_message is not None:
        out["error_message"] = error_message
    return out


class AggregateTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc).replace(tzinfo=None)

    def test_dropping_out_of_window_tasks(self):
        in_window = self.now - timedelta(days=5)
        far_past = self.now - timedelta(days=100)
        out = aggregate(
            [
                _task("a", created_at=in_window),
                _task("b", created_at=far_past),
            ],
            range_days=30,
        )
        self.assertEqual(out.status_distribution, {"completed": 1})
        self.assertEqual(sum(p.submitted for p in out.submit_trend), 1)

    def test_runtime_only_from_completed_with_positive_delta(self):
        c = self.now - timedelta(days=1)
        out = aggregate(
            [
                # Healthy completed: 60s
                _task("ok", created_at=c, started_at=c, completed_at=c + timedelta(seconds=60)),
                # Failed task — runtime ignored even if timestamps present
                _task("bad", status="failed", created_at=c, started_at=c,
                      completed_at=c + timedelta(seconds=99),
                      error_message="boom"),
                # Clock skew (negative delta) — dropped
                _task("skew", created_at=c, started_at=c, completed_at=c - timedelta(seconds=10)),
                # Missing completed_at — dropped
                _task("running", status="running", created_at=c, started_at=c),
            ],
            range_days=30,
        )
        rt = out.runtime_by_mode.get("promoters")
        self.assertIsNotNone(rt)
        self.assertEqual(rt.count, 1)
        self.assertEqual(rt.samples, [60.0])

    def test_error_messages_normalize_to_collapse_task_ids(self):
        c = self.now - timedelta(days=1)
        out = aggregate(
            [
                _task("a", status="failed", created_at=c,
                      error_message="Command failed in phase2_abc1234567890def: bedtools"),
                _task("b", status="failed", created_at=c,
                      error_message="Command failed in phase2_fffeeedd00112233: bedtools"),
                _task("c", status="failed", created_at=c,
                      error_message="Disk full"),
            ],
            range_days=30,
        )
        # Two of three failures share a normalized message; <id> bucket.
        counts = {e.message: e.count for e in out.top_errors}
        self.assertEqual(sum(counts.values()), 3)
        # The bedtools-pair collapsed to one row with count=2.
        self.assertTrue(any(c == 2 for c in counts.values()),
                        f"expected a collapsed bucket with count=2, got {counts}")

    def test_trend_is_zero_filled_across_window(self):
        # One task today; rest of the 7-day window should be zeros, not
        # missing days. A chart consumer should see exactly 7 points.
        c = self.now - timedelta(hours=1)
        out = aggregate([_task("a", created_at=c)], range_days=7)
        self.assertEqual(len(out.submit_trend), 7)
        # Total submitted across the window == 1
        self.assertEqual(sum(p.submitted for p in out.submit_trend), 1)
        # All zeros except one cell
        non_zero = [p for p in out.submit_trend if p.submitted]
        self.assertEqual(len(non_zero), 1)

    def test_top_errors_ignores_non_failed(self):
        c = self.now - timedelta(days=1)
        out = aggregate(
            [
                _task("a", status="completed", created_at=c,
                      error_message="ignored"),
                _task("b", status="failed", created_at=c,
                      error_message="real"),
            ],
            range_days=30,
        )
        self.assertEqual([e.message for e in out.top_errors], ["real"])


class HelperTests(unittest.TestCase):
    def test_percentile_basic(self):
        self.assertEqual(_percentile([], 0.5), None)
        self.assertEqual(_percentile([5.0], 0.5), 5.0)
        # Linear interpolation between two values
        self.assertAlmostEqual(_percentile([1.0, 2.0, 3.0, 4.0], 0.5), 2.5)

    def test_normalize_error_scrubs_hex_and_phase_ids(self):
        self.assertEqual(
            _normalize_error("Command failed in phase2_abc1234567890def: x"),
            "Command failed in <id>: x",
        )
        self.assertEqual(
            _normalize_error("error abc1234567890def end"),
            "error <id> end",
        )

    def test_normalize_error_truncates(self):
        long = "x" * 500
        self.assertLessEqual(len(_normalize_error(long)), 200)


if __name__ == "__main__":
    unittest.main()
