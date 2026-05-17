"""Admin task statistics endpoint.

One aggregation endpoint that walks ``config.TASKS_DIR/*.json`` and
returns four shapes the dashboard plots in a single mount:

- ``submit_trend``       — daily counts (submitted / completed / failed /
  cancelled) over the window, with missing days zero-filled so the
  x-axis stays continuous
- ``status_distribution``— total task count per persisted status across
  the window
- ``runtime_by_mode``    — per-mode runtime samples + p50/p95 (only
  completed tasks, runtime = completed_at − started_at)
- ``top_errors``         — top-10 most-common normalized error messages
  with task-id-like tokens scrubbed so multiple tasks failing the same
  way collapse into one row

Why one endpoint: the dashboard renders all four panels at once, so a
combined response avoids four round-trips and four parses of the same
file set. 200 tasks parse in <50 ms, so we don't cache.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ...config import config
from .admin import require_admin


router = APIRouter(prefix="/admin", tags=["admin"])


class TrendPoint(BaseModel):
    date: str
    submitted: int
    completed: int
    failed: int
    cancelled: int


class RuntimeStats(BaseModel):
    count: int
    p50: Optional[float]
    p95: Optional[float]
    samples: list[float]


class TopError(BaseModel):
    message: str
    count: int


class AdminStatsResponse(BaseModel):
    range_days: int
    submit_trend: list[TrendPoint]
    status_distribution: dict[str, int]
    runtime_by_mode: dict[str, RuntimeStats]
    top_errors: list[TopError]


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _percentile(samples: list[float], p: float) -> Optional[float]:
    if not samples:
        return None
    s = sorted(samples)
    k = (len(s) - 1) * p
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


# Scrub task-id-like hex / phaseN_ prefixes so e.g. "phase2_ab12cd..." and
# "phase2_99ee77..." with the same underlying error collapse to one row.
_TASK_ID_RE = re.compile(r"\b(phase\d+_)?[0-9a-f]{8,}\b")


def _normalize_error(msg: str) -> str:
    msg = _TASK_ID_RE.sub("<id>", msg)
    msg = " ".join(msg.split())
    return msg[:200]


def aggregate(tasks: list[dict], range_days: int) -> AdminStatsResponse:
    """Pure aggregator — fed pre-loaded task dicts so tests can stub the FS."""
    now = datetime.now(timezone.utc)
    # created_at is persisted without tz info; compare naive-to-naive to
    # avoid TZ-mixing exceptions. The cutoff just needs to be consistent.
    cutoff_naive = (now - timedelta(days=range_days)).replace(tzinfo=None)

    daily: dict[str, dict[str, int]] = defaultdict(
        lambda: {"submitted": 0, "completed": 0, "failed": 0, "cancelled": 0}
    )
    status_counts: Counter = Counter()
    runtime_by_mode: dict[str, list[float]] = defaultdict(list)
    error_bucket: Counter = Counter()

    for t in tasks:
        created = _parse_iso(t.get("created_at"))
        if not created:
            continue
        created_naive = created.replace(tzinfo=None) if created.tzinfo else created
        if created_naive < cutoff_naive:
            continue

        status = (t.get("status") or "unknown").lower()
        status_counts[status] += 1

        day = created_naive.strftime("%Y-%m-%d")
        daily[day]["submitted"] += 1
        if status in ("completed", "failed", "cancelled"):
            daily[day][status] += 1

        started = _parse_iso(t.get("started_at"))
        completed = _parse_iso(t.get("completed_at"))
        if started and completed and status == "completed":
            mode = t.get("mode") or "unknown"
            secs = (completed - started).total_seconds()
            if secs > 0:
                runtime_by_mode[mode].append(secs)

        if status == "failed":
            err = t.get("error_message")
            if isinstance(err, str) and err.strip():
                error_bucket[_normalize_error(err)] += 1

    # Zero-fill the trend across the whole window so the chart is dense.
    trend: list[TrendPoint] = []
    for i in range(range_days - 1, -1, -1):
        d = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        cell = daily.get(d, {"submitted": 0, "completed": 0, "failed": 0, "cancelled": 0})
        trend.append(TrendPoint(date=d, **cell))

    runtime_out: dict[str, RuntimeStats] = {}
    for mode, samples in runtime_by_mode.items():
        runtime_out[mode] = RuntimeStats(
            count=len(samples),
            p50=_percentile(samples, 0.50),
            p95=_percentile(samples, 0.95),
            samples=samples,
        )

    top = [TopError(message=m, count=c) for m, c in error_bucket.most_common(10)]

    return AdminStatsResponse(
        range_days=range_days,
        submit_trend=trend,
        status_distribution=dict(status_counts),
        runtime_by_mode=runtime_out,
        top_errors=top,
    )


def _load_tasks() -> list[dict]:
    out: list[dict] = []
    for p in config.TASKS_DIR.glob("*.json"):
        try:
            out.append(json.loads(p.read_text()))
        except (json.JSONDecodeError, OSError):
            continue
    return out


@router.get(
    "/stats",
    dependencies=[Depends(require_admin)],
    response_model=AdminStatsResponse,
)
def get_stats(days: int = Query(default=30, ge=1, le=365)) -> AdminStatsResponse:
    return aggregate(_load_tasks(), days)
