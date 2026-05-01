"""Per-stage status derivation for PMET tasks.

The pipeline has four conceptual stages: indexing → pairing → heatmap →
zip. The `status` field on a task is binary-ish (pending/running/
completed/failed/cancelled) and loses the information of *which*
stage produced output and which one didn't. That mismatch is "Problem 4
— task.status is a liar" in TODO.md.

This module derives a per-stage view by inspecting the on-disk
artifacts under results/app/<task_id>/. Pure function with no I/O
beyond stat / glob, so it's cheap to call on every GET /tasks/{id}.

The persisted `status` is kept as the source of truth — `infer_stages`
only annotates *what's there now*. Frontend uses both: status drives
the badge colour, stages drive the timeline + warnings panel.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _file_nonempty(p: Path) -> bool:
    try:
        return p.is_file() and p.stat().st_size > 0
    except OSError:
        return False


def _has_heatmap(plot_dir: Path) -> bool:
    if not plot_dir.is_dir():
        return False
    try:
        return any(plot_dir.glob("heatmap*.png"))
    except OSError:
        return False


def infer_stages(task_meta: dict, task_dir: Path) -> list[dict[str, Any]]:
    """Return an ordered list of stage descriptors derived from the
    on-disk task directory. Each item:
        {"name": str, "state": str, "note": Optional[str]}
    state ∈ {"pending", "running", "completed", "failed", "skipped"}.

    `task_dir` is results/app/<task_id>/. The .zip companion is
    expected at task_dir.parent / f"{task_dir.name}.zip".
    """
    mode = task_meta.get("mode", "")
    status = task_meta.get("status", "pending")
    is_failed = status == "failed"
    is_running = status == "running"
    is_cancelled = status == "cancelled"

    has_indexing = _file_nonempty(task_dir / "indexing" / "universe.txt")
    has_motif_output = _file_nonempty(task_dir / "pairing" / "motif_output.txt")
    has_heatmap = _has_heatmap(task_dir / "pairing" / "plot")
    has_zip = (task_dir.parent / f"{task_dir.name}.zip").is_file()

    stages: list[dict[str, Any]] = []

    # ------- indexing -------
    if mode == "promoters_pre":
        # Distinct from `skipped` so the UI can paint a neutral colour
        # — this is by-design absence, not a warning.
        stages.append({
            "name": "indexing",
            "state": "precomputed",
            "note": "uses precomputed index",
        })
    elif has_indexing:
        stages.append({"name": "indexing", "state": "completed"})
    elif is_cancelled:
        stages.append({"name": "indexing", "state": "skipped"})
    elif is_failed:
        # No indexing artifacts AND task failed → indexing is where it
        # broke (or it never ran because preflight failed; either way
        # we surface that as failed at the indexing stage).
        stages.append({"name": "indexing", "state": "failed"})
    elif is_running:
        stages.append({"name": "indexing", "state": "running"})
    else:
        stages.append({"name": "indexing", "state": "pending"})

    indexing_ok = stages[0]["state"] in ("completed", "skipped", "precomputed")

    # ------- pairing -------
    if has_motif_output:
        stages.append({"name": "pairing", "state": "completed"})
    elif is_cancelled:
        stages.append({"name": "pairing", "state": "skipped"})
    elif is_failed:
        if indexing_ok:
            stages.append({"name": "pairing", "state": "failed"})
        else:
            # Indexing already failed; pairing never started.
            stages.append({"name": "pairing", "state": "pending"})
    elif is_running and indexing_ok:
        stages.append({"name": "pairing", "state": "running"})
    else:
        stages.append({"name": "pairing", "state": "pending"})

    pairing_ok = stages[1]["state"] == "completed"

    # ------- heatmap (always best-effort) -------
    if has_heatmap:
        stages.append({"name": "heatmap", "state": "completed"})
    elif pairing_ok:
        # Pairing wrote motif_output.txt but no heatmap PNG. Either
        # the R step crashed (most common: ggsave dim panic) or it
        # was deliberately skipped. Either way, scientific data is
        # complete — surface as 'skipped' with a note so the UI can
        # explain it.
        if is_failed:
            stages.append({
                "name": "heatmap",
                "state": "skipped",
                "note": "rendering failed; motif_output.txt is complete",
            })
        elif is_running:
            stages.append({"name": "heatmap", "state": "running"})
        else:
            stages.append({
                "name": "heatmap",
                "state": "skipped",
                "note": "no heatmap output found",
            })
    elif is_cancelled:
        stages.append({"name": "heatmap", "state": "skipped"})
    else:
        stages.append({"name": "heatmap", "state": "pending"})

    # ------- zip -------
    if has_zip:
        stages.append({"name": "zip", "state": "completed"})
    elif is_cancelled:
        stages.append({"name": "zip", "state": "skipped"})
    elif pairing_ok and is_failed:
        # Late-stage failure (heatmap or zip itself) but the
        # scientific output is on disk. Mark zip as skipped so the
        # warnings panel can point users at /partial-result.
        stages.append({
            "name": "zip",
            "state": "skipped",
            "note": "late-stage failure; partial result still available",
        })
    elif is_running and pairing_ok:
        stages.append({"name": "zip", "state": "running"})
    else:
        stages.append({"name": "zip", "state": "pending"})

    return stages


def derive_warnings(stages: list[dict[str, Any]]) -> list[str]:
    """Pull human-readable warning strings from any stage that ended
    in `skipped` with an explanatory note. The mode-design absence
    (e.g. promoters_pre indexing) gets its own `precomputed` state and
    is intentionally NOT a warning here.
    """
    out: list[str] = []
    for s in stages:
        if s.get("state") != "skipped":
            continue
        note = s.get("note")
        if note:
            out.append(f"{s['name']}: {note}")
    return out


def derive_effective_status(persisted_status: str, stages: list[dict[str, Any]]) -> str:
    """Return a richer status label suitable for the UI badge.

    Two values get synthesised on top of the persisted enum:

      - `completed_with_warnings`: persisted is `completed` but a stage
        was skipped with a user-facing warning (currently the
        "heatmap rendered but with caveats" path).
      - `partial_success`: persisted is `failed` BUT the pairing
        stage produced motif_output.txt (so the user has actual
        scientific output to grab via partial_result_link). Painting
        a hard red "Failed" badge in that case under-reports the
        outcome — the late-stage failure didn't lose the data.

    Other persisted statuses pass through unchanged. This keeps the
    DB enum stable and lets the frontend distinguish three flavours
    of "didn't go cleanly".
    """
    if persisted_status == "completed":
        has_real_warning = any(
            s.get("state") == "skipped" and s.get("note")
            for s in stages
        )
        return "completed_with_warnings" if has_real_warning else "completed"
    if persisted_status == "failed":
        pairing_ok = any(
            s.get("name") == "pairing" and s.get("state") == "completed"
            for s in stages
        )
        return "partial_success" if pairing_ok else "failed"
    return persisted_status
