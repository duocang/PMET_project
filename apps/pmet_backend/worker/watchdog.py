"""Liveness watchdog for PMET tasks.

A task is "alive" while its progress.json is being touched. The PMET
workflow scripts call emit_progress (scripts/lib/progress.sh) at every
stage boundary; a task that hasn't emitted progress for
LIVENESS_TIMEOUT_SEC seconds is treated as stuck — the bash subprocess
is process-tree-killed and the task is marked failed.

This addresses the "long-running task" problem more honestly than a
wall-clock cap: a CIS-BP2 pairing run that takes 12 minutes should
*not* be killed simply because >10 min elapsed. It will not be killed
here either, as long as it keeps emitting progress between stages.
Conversely a deadlocked task that hasn't moved in 15 min IS killed,
freeing its worker slot.

Runs in its own container so it can fire even when all celery worker
slots are saturated. See deploy/docker-compose.yml service
`liveness-watchdog`.

Tunables (env, with defaults from config.py):
  - PMET_LIVENESS_TIMEOUT_SEC : staleness threshold (default 900 s)
  - PMET_WATCHDOG_POLL_SEC    : sweep cadence (default 60 s)

Caveat: progress is emitted at *stage boundaries*, not within stages.
A single fimo scan or pair-test loop can today exceed 15 min on the
biggest motif libraries (CIS-BP2), so 900 s is conservative; tasks
inside one long stage that legitimately take longer than the threshold
will be false-positive-killed. Mitigation: bump the env var per
deployment, or add finer-grained emit_progress calls inside the
expensive loops (see TODO.md).
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..config import config
from ..proc import kill_process_tree


def _load_meta(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _staleness_seconds(task_dir: Path, started_at: Optional[str]) -> Optional[float]:
    """How long has this task been silent? None if we can't tell."""
    progress_file = task_dir / "progress.json"
    if progress_file.exists():
        return time.time() - progress_file.stat().st_mtime

    # No progress file yet. The bash pipeline may not have reached the
    # first emit_progress call. Fall back to wall-clock since started_at
    # so a task that wedges before any stage emit still gets caught.
    if started_at:
        try:
            started = datetime.fromisoformat(started_at)
        except ValueError:
            return None
        return (datetime.utcnow() - started).total_seconds()

    return None


def _kill_if_stale(task_json: Path, threshold_sec: int) -> Optional[str]:
    """Inspect one task JSON. Kill + mark failed if stale. Returns the
    reason string when killed, None otherwise."""
    meta = _load_meta(task_json)
    if not meta or meta.get("status") != "running":
        return None
    task_id = meta.get("task_id")
    if not task_id:
        return None

    task_dir = config.RESULT_DIR / task_id
    age = _staleness_seconds(task_dir, meta.get("started_at"))
    if age is None or age < threshold_sec:
        return None

    reason = (
        f"liveness probe: no progress for {int(age)}s "
        f"(threshold {threshold_sec}s)"
    )

    # Mark failed BEFORE killing so the worker's outer except block
    # sees a terminal state and won't overwrite it on retry.
    meta["status"] = "failed"
    meta["error_message"] = reason
    meta["completed_at"] = datetime.utcnow().isoformat()
    task_json.write_text(json.dumps(meta, indent=2))

    pid_file = task_dir / "worker.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            kill_process_tree(pid)
        except (ValueError, OSError):
            pass

    return reason


def main() -> None:
    threshold = config.LIVENESS_TIMEOUT_SEC
    poll = int(os.environ.get("PMET_WATCHDOG_POLL_SEC", "60"))
    print(
        f"[liveness] watchdog started — threshold={threshold}s, "
        f"poll={poll}s, tasks_dir={config.TASKS_DIR}",
        flush=True,
    )
    while True:
        try:
            for task_json in config.TASKS_DIR.glob("*.json"):
                reason = _kill_if_stale(task_json, threshold)
                if reason is not None:
                    print(
                        f"[liveness] killed {task_json.stem}: {reason}",
                        flush=True,
                    )
        except Exception as e:  # pragma: no cover — defensive
            print(f"[liveness] sweep error: {e}", flush=True)
        time.sleep(poll)


if __name__ == "__main__":
    main()
