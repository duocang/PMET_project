"""Admin-only task-level endpoints.

Three operations on a single task:

- ``GET /admin/task/<id>/debug``  — full task_meta dump + stderr tail
  (last 50 lines from ``RESULT_DIR/<id>/stderr.log`` if present)
- ``PUT /admin/task/<id>/note``   — set / clear an admin-authored note,
  rendered as a banner on the task detail page for the user
- ``POST /admin/task/<id>/rerun`` — duplicate the task metadata under
  a fresh task_id and queue it for the worker. The user receives a
  notification email when the rerun starts.

All three are guarded by ``require_admin`` and audited.
"""

from __future__ import annotations

import json
import re
import secrets
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ...config import config
from ...services import audit
from .admin import require_admin, _client_ip


router = APIRouter(prefix="/admin/task", tags=["admin"])


def _task_meta_path(task_id: str) -> Path:
    return config.TASKS_DIR / f"{task_id}.json"


def _load_meta(task_id: str) -> dict:
    p = _task_meta_path(task_id)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Task not found")
    try:
        data = json.loads(p.read_text())
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Task metadata is corrupt")
    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail="Task metadata is corrupt")
    return data


@router.get("/{task_id}/debug", dependencies=[Depends(require_admin)])
async def task_debug(task_id: str):
    """Pretty-printed metadata + stderr tail. Admin-only — exposes
    things normal users shouldn't see (other clusters' email patterns,
    chosen IC threshold rationale, raw shell error messages).
    """
    meta = _load_meta(task_id)
    log_path = config.RESULT_DIR / task_id / "stderr.log"
    stderr_tail: Optional[list[str]] = None
    if log_path.exists():
        try:
            text = log_path.read_text(errors="replace")
            # Last 50 lines is enough to spot the failure; full file
            # could be many MB if the workflow piped a verbose tool.
            stderr_tail = text.splitlines()[-50:]
        except OSError:
            stderr_tail = None
    return {
        "task_id": task_id,
        "meta": meta,
        "stderr_tail": stderr_tail,
    }


class AdminNote(BaseModel):
    note: Optional[str] = None  # empty / None clears the note


@router.put("/{task_id}/note", dependencies=[Depends(require_admin)])
async def task_set_note(task_id: str, payload: AdminNote, request: Request):
    """Attach / clear an admin-authored note on a task. Visible to the
    user as a banner on the task detail page (so the admin can say
    "your task is delayed because the worker is rebooting").
    """
    meta = _load_meta(task_id)
    text = (payload.note or "").strip()
    if text:
        meta["admin_note"] = text[:1000]  # hard cap so the banner stays legible
    else:
        meta.pop("admin_note", None)
    _task_meta_path(task_id).write_text(json.dumps(meta, indent=2))
    audit.emit(
        action="task_note",
        ok=True,
        ip=_client_ip(request),
        target=task_id,
        detail={"len": len(text)},
    )
    return {"task_id": task_id, "admin_note": meta.get("admin_note")}


# Same constraints the issue-session endpoint uses for new task_ids.
# Keep the format consistent so existing downstream code (path
# whitelisting, regex filters in list_tasks) keeps working.
_RERUN_PREFIX = "rerun"
_TASK_ID_RE = re.compile(r"^[a-zA-Z0-9_]{1,80}$")


def _rerun_task_id(orig: str) -> str:
    """Generate a fresh, syntactically-valid task_id for the duplicate."""
    safe = "".join(c for c in orig if c.isalnum() or c == "_")[:40]
    return f"{_RERUN_PREFIX}_{safe}_{secrets.token_hex(4)}"


@router.post("/{task_id}/rerun", dependencies=[Depends(require_admin)])
async def task_rerun(task_id: str, request: Request):
    """Duplicate the task with a fresh task_id and queue the rerun.

    Upload paths in the source metadata must still resolve on disk —
    if a previous retention sweep deleted them the rerun would fail
    inside the workflow, so refuse upfront with 409.
    """
    src = _load_meta(task_id)

    # Validate that referenced input files (if any) still exist.
    # The frontend uploads land under RESULT_DIR/<task_id>/upload/, and
    # the task JSON stores them as relative paths like
    # "results/<task_id>/upload/genes.txt" (RESULT_DIR-relative) or as
    # data/precomputed_indexes/... for the pre-computed mode. We only
    # validate the upload-style paths here; pre-computed catalog paths
    # are owned by the server and not user-deletable.
    missing: list[str] = []
    for key in ("genes_file", "fasta_file", "gff3_file", "meme_file"):
        rel = src.get(key)
        if not isinstance(rel, str) or not rel:
            continue
        if rel.startswith("data/precomputed_indexes/"):
            continue
        # Resolve against project root since the meta stores
        # repo-relative paths (see tasks.py create_task).
        abs_p = config.PROJECT_ROOT / rel
        if not abs_p.exists():
            missing.append(rel)
    if missing:
        raise HTTPException(
            status_code=409,
            detail=f"Source files no longer on disk: {', '.join(missing)}",
        )

    new_id = _rerun_task_id(task_id)
    if not _TASK_ID_RE.match(new_id):
        raise HTTPException(status_code=500, detail="Generated task_id failed validation")

    new_meta = {**src}
    new_meta["task_id"] = new_id
    new_meta["status"] = "pending"
    new_meta["created_at"] = datetime.utcnow().isoformat()
    new_meta["rerun_of"] = task_id
    new_meta.pop("started_at", None)
    new_meta.pop("completed_at", None)
    new_meta.pop("cancelled_at", None)
    new_meta.pop("cancelled_by", None)
    new_meta.pop("cancel_reason", None)
    new_meta.pop("error_message", None)
    new_meta.pop("result_link", None)
    new_meta.pop("partial_result_link", None)
    new_meta.pop("partial_result_size_bytes", None)
    new_meta.pop("admin_note", None)

    new_path = _task_meta_path(new_id)
    new_path.parent.mkdir(parents=True, exist_ok=True)
    new_path.write_text(json.dumps(new_meta, indent=2))

    # Queue with celery. Match the calling convention used by
    # tasks.create_task (task_meta dict + task_dir str). The rerun gets
    # its own output directory; we don't share with the original so
    # cleanup / display can treat them independently.
    new_task_dir = config.RESULT_DIR / new_id
    new_task_dir.mkdir(parents=True, exist_ok=True)
    try:
        from ...worker.tasks.pmet import run_pmet_task
        run_pmet_task.delay(new_meta, str(new_task_dir))
    except Exception as e:
        # Roll back the metadata + dir creation so the task list doesn't
        # show a phantom pending task that never actually queued.
        try:
            new_path.unlink()
        except OSError:
            pass
        try:
            new_task_dir.rmdir()
        except OSError:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to queue: {e}")

    audit.emit(
        action="task_rerun",
        ok=True,
        ip=_client_ip(request),
        target=new_id,
        detail={"rerun_of": task_id},
    )
    return {"task_id": new_id, "rerun_of": task_id}
