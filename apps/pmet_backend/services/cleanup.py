"""Result retention cleaner.

Companion to the ``result_retention_days`` admin setting. Deletes
per-task artefacts older than the threshold:

- ``RESULT_DIR/<task_id>/`` (output tree)
- ``RESULT_DIR/<task_id>.zip`` (downloadable bundle)
- ``RESULT_DIR/tasks/<task_id>.json`` (task metadata)

A task's age is its ``created_at`` from the metadata JSON. If the JSON
is gone but the directory / zip linger, they're treated as orphans and
deleted alongside any matching task_id during the next sweep — the
``orphans`` count in the report tells the operator how often this
happens.

This module exposes pure functions; the API route ties them to the
admin endpoint, and a future cron / systemd timer can call them
directly.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from ..config import config


def _parse_iso(s: Optional[str]):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _eligible_task_ids(retention_days: int, now: Optional[datetime] = None) -> list[str]:
    """Return task_ids whose ``created_at`` is older than the cutoff."""
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now - timedelta(days=retention_days)
    eligible: list[str] = []
    if not config.TASKS_DIR.exists():
        return eligible
    for p in config.TASKS_DIR.glob("*.json"):
        try:
            data = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        created = _parse_iso(data.get("created_at"))
        if not created:
            continue
        created_naive = created.replace(tzinfo=None) if created.tzinfo else created
        if created_naive < cutoff:
            eligible.append(data.get("task_id") or p.stem)
    return eligible


def count_eligible(retention_days: int) -> int:
    """Cheap preview — how many tasks would the next sweep remove?"""
    if retention_days <= 0:
        return 0
    return len(_eligible_task_ids(retention_days))


def run(retention_days: int, dry_run: bool = False) -> dict:
    """Sweep once. Returns a summary report for the dashboard / audit log.

    ``dry_run=True`` enumerates without deleting — used by the preview
    button to show "would remove N items" before the operator commits.
    """
    if retention_days <= 0:
        return {
            "retention_days": retention_days,
            "skipped": True,
            "reason": "retention_days not configured (set on the dashboard)",
            "removed_dirs": 0,
            "removed_zips": 0,
            "removed_metas": 0,
            "errors": [],
        }

    task_ids = _eligible_task_ids(retention_days)
    removed_dirs = 0
    removed_zips = 0
    removed_metas = 0
    errors: list[str] = []

    for tid in task_ids:
        # Output directory
        out_dir = config.RESULT_DIR / tid
        if out_dir.exists():
            if dry_run:
                removed_dirs += 1
            else:
                try:
                    shutil.rmtree(out_dir)
                    removed_dirs += 1
                except OSError as e:
                    errors.append(f"rmtree {out_dir}: {e}")

        # Bundle zip
        zip_path = config.RESULT_DIR / f"{tid}.zip"
        if zip_path.exists():
            if dry_run:
                removed_zips += 1
            else:
                try:
                    zip_path.unlink()
                    removed_zips += 1
                except OSError as e:
                    errors.append(f"unlink {zip_path}: {e}")

        # Metadata JSON (delete last so we can identify the task above)
        meta = config.TASKS_DIR / f"{tid}.json"
        if meta.exists():
            if dry_run:
                removed_metas += 1
            else:
                try:
                    meta.unlink()
                    removed_metas += 1
                except OSError as e:
                    errors.append(f"unlink {meta}: {e}")

    return {
        "retention_days": retention_days,
        "dry_run": dry_run,
        "candidates": len(task_ids),
        "removed_dirs": removed_dirs,
        "removed_zips": removed_zips,
        "removed_metas": removed_metas,
        "errors": errors,
    }
