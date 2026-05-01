from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from datetime import datetime
from pathlib import Path
from typing import Optional
import json

from pydantic import BaseModel

from ..models.task import TaskCreate, TaskResponse, TaskStatus, TaskMode, TaskListResponse
from ...config import config
from ...services.storage import StorageService
from ...services.mail import MailService
from ...services.stage_status import infer_stages, derive_warnings, derive_effective_status
from .admin import require_admin

router = APIRouter(prefix="/tasks", tags=["tasks"])
storage = StorageService()


class CancelPayload(BaseModel):
    reason: Optional[str] = None


class EstimatePayload(BaseModel):
    """Inputs for /api/tasks/estimate. Each field is optional; the backend
    will read the file paths if the precomputed counts aren't passed in."""
    mode: TaskMode
    ncpu: Optional[int] = None
    n_motifs: Optional[int] = None
    n_target_genes: Optional[int] = None
    n_intervals: Optional[int] = None
    fasta_size_bytes: Optional[int] = None
    genes_file: Optional[str] = None
    fasta_file: Optional[str] = None
    meme_file: Optional[str] = None
    premade_index: Optional[str] = None


def _resolve_safe_input(rel: Optional[str]):
    """Resolve a payload-supplied path against PROJECT_ROOT, requiring it to
    land inside one of the read-allowed roots. Returns None on any rule
    miss — callers treat that as "feature unknown" and fall back to zeros
    in the estimate.

    Rules:
      - Must be a non-empty string
      - After `resolve(strict=False)` must live under PROJECT_ROOT/data/ or
        PROJECT_ROOT/results/ (the upload dirs)
      - Must be a regular file (no symlink, fifo, device)

    The estimate endpoint is unauthenticated and gets to read motif counts,
    line counts, and file sizes — without these guards a caller could pass
    `../../etc/passwd` to sniff line counts of arbitrary readable files,
    or point at /proc/kcore to OOM the API process.
    """
    if not rel or not isinstance(rel, str):
        return None
    root = config.PROJECT_ROOT.resolve()
    try:
        candidate = (root / rel).resolve(strict=False)
    except (OSError, RuntimeError):
        return None

    allowed_prefixes = (root / "data", root / "results")
    if not any(
        candidate == p or p in candidate.parents for p in allowed_prefixes
    ):
        return None
    if not candidate.is_file():
        return None
    return candidate


def _resolve_safe_index_dir(rel: Optional[str]):
    """Resolve a precomputed-index directory under data/precomputed_indexes."""
    if not rel or not isinstance(rel, str):
        return None
    root = config.PROJECT_ROOT.resolve()
    indexing_root = config.PRECOMPUTED_INDEXING_DIR.resolve()
    try:
        candidate = (root / rel).resolve(strict=False)
    except (OSError, RuntimeError):
        return None

    if not (candidate == indexing_root or indexing_root in candidate.parents):
        return None
    if not candidate.is_dir():
        return None
    return candidate


# Safety cap on file reads inside the estimate endpoint. Above this we just
# return the size or 0 instead of streaming the whole file.
_ESTIMATE_MAX_READ_BYTES = 256 * 1024 * 1024  # 256 MB


def _count_meme_motifs(path) -> int:
    if not path:
        return 0
    try:
        if path.stat().st_size > _ESTIMATE_MAX_READ_BYTES:
            return 0
        with path.open("r", errors="replace") as fh:
            return sum(1 for line in fh if line.startswith("MOTIF "))
    except OSError:
        return 0


def _count_index_motifs(index_dir) -> int:
    if not index_dir:
        return 0
    hits_dir = index_dir / "fimohits"
    if not hits_dir.is_dir():
        return 0
    try:
        return sum(1 for path in hits_dir.iterdir() if path.is_file())
    except OSError:
        return 0


def _count_lines(path) -> int:
    if not path:
        return 0
    try:
        if path.stat().st_size > _ESTIMATE_MAX_READ_BYTES:
            return 0
        with path.open("r", errors="replace") as fh:
            return sum(1 for line in fh if line.strip())
    except OSError:
        return 0


def _file_size(path) -> int:
    try:
        return path.stat().st_size if path else 0
    except OSError:
        return 0


def _premade_index_summary(premade_index: Optional[str]) -> dict:
    """Extract species and motif database ids from a precomputed index path."""
    if not premade_index:
        return {}
    parts = Path(premade_index).parts
    try:
        idx = parts.index("precomputed_indexes")
    except ValueError:
        return {}
    if len(parts) <= idx + 2:
        return {}
    return {
        "indexing_species": parts[idx + 1],
        "indexing_motif_db": parts[idx + 2],
    }


def _load_runtime_calibration() -> dict:
    """Hot-read coefficients on each estimate call so admins can tune without
    restarting the worker."""
    path = config.PROJECT_ROOT / "data" / "configure" / "runtime_calibration.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _estimate_runtime_seconds(meta: dict, calib: dict) -> int:
    """Return predicted seconds for the given inputs. Always >= 5s so the
    UI never shows a nonsensically small range."""
    mode = meta.get("mode")
    ncpu = max(1, int(meta.get("ncpu") or config.NCPU or 1))
    n_motifs = max(0, int(meta.get("n_motifs") or 0))
    n_target_genes = max(0, int(meta.get("n_target_genes") or 0))

    if mode == TaskMode.PROMOTERS_PRE.value:
        c = calib.get("promoters_pre", {})
        seconds = (
            c.get("base_seconds", 10)
            + c.get("per_target_gene", 0.02) * n_target_genes
            + c.get("per_motif_per_cpu", 0.2) * n_motifs / ncpu
            + c.get("per_motif_per_thousand_target_genes_per_cpu", 1.0)
            * n_motifs
            * (n_target_genes / 1000.0)
            / ncpu
        )
    elif mode == TaskMode.INTERVALS.value:
        c = calib.get("intervals", {})
        n_intervals = max(0, int(meta.get("n_intervals") or n_target_genes or 0))
        seconds = (
            c.get("base_seconds", 20)
            + c.get("per_motif_per_thousand_intervals_per_cpu", 1.0)
            * n_motifs
            * (n_intervals / 1000.0)
            / ncpu
        )
    elif mode == TaskMode.PROMOTERS.value:
        c = calib.get("promoters", {})
        fasta_mb = max(0.0, int(meta.get("fasta_size_bytes") or 0) / (1024 * 1024))
        seconds = (
            c.get("base_seconds", 60)
            + c.get("per_motif_per_fasta_mb_per_cpu", 0.025) * n_motifs * fasta_mb / ncpu
            + c.get("per_target_gene", 0.02) * n_target_genes
        )
    else:
        seconds = 60

    return max(5, int(round(seconds)))


def _runtime_estimate_response(inputs: dict) -> dict:
    """Build the estimate response from either EstimatePayload or task meta."""
    mode_raw = inputs.get("mode")
    mode = mode_raw.value if isinstance(mode_raw, TaskMode) else str(mode_raw)

    n_motifs = inputs.get("n_motifs")
    if n_motifs is None and mode == TaskMode.PROMOTERS_PRE.value:
        n_motifs = _count_index_motifs(_resolve_safe_index_dir(inputs.get("premade_index")))
    elif n_motifs is None:
        n_motifs = _count_meme_motifs(_resolve_safe_input(inputs.get("meme_file")))

    n_target_genes = inputs.get("n_target_genes")
    if n_target_genes is None:
        n_target_genes = _count_lines(_resolve_safe_input(inputs.get("genes_file")))

    fasta_size = inputs.get("fasta_size_bytes")
    if fasta_size is None:
        fasta_size = _file_size(_resolve_safe_input(inputs.get("fasta_file")))

    n_intervals = inputs.get("n_intervals")
    if n_intervals is None and mode == TaskMode.INTERVALS.value:
        # Intervals lives in the gene_file slot in the submit form.
        n_intervals = _count_lines(_resolve_safe_input(inputs.get("genes_file")))

    features = {
        "mode": mode,
        "ncpu": inputs.get("ncpu") or config.NCPU,
        "n_motifs": n_motifs or 0,
        "n_target_genes": n_target_genes or 0,
        "n_intervals": n_intervals or 0,
        "fasta_size_bytes": fasta_size or 0,
    }
    seconds = _estimate_runtime_seconds(features, _load_runtime_calibration())
    return {
        "estimate_seconds": seconds,
        "lower_seconds": seconds,
        "upper_seconds": seconds * 2,
        "factors": features,
    }


def _locate_motif_output(task_id: str) -> Optional[Path]:
    """Return the path to motif_output.txt if the pairing stage produced
    one for this task, else None.

    Web tasks (promoters_pre / promoters / intervals) write to
    `<task_dir>/pairing/motif_output.txt`. We only check that one
    canonical location — Elements mode (CLI-only) uses a different
    layout but is not exposed via the web API.
    """
    candidate = config.RESULT_DIR / task_id / "pairing" / "motif_output.txt"
    return candidate if candidate.is_file() and candidate.stat().st_size > 0 else None


def _kill_process_tree(pid: int) -> list[int]:
    """SIGTERM (then SIGKILL after 5s) the process and every descendant.

    Used to make a task termination *thorough* — the worker spawns shell
    pipelines that fork their own children, so killing only the top PID
    leaves orphans running. Returns the list of PIDs we attempted to
    terminate so the caller can audit if needed.
    """
    import psutil

    killed: list[int] = []
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return killed

    procs = [parent] + parent.children(recursive=True)
    for p in procs:
        try:
            p.terminate()
            killed.append(p.pid)
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(procs, timeout=5)
    for p in alive:
        try:
            p.kill()
        except psutil.NoSuchProcess:
            pass
    return killed


@router.post("", response_model=TaskResponse)
async def create_task(task: TaskCreate):
    """Create a new PMET task"""
    task_id = storage.generate_task_id(task.email, override=task.task_id)
    task_dir = storage.create_task_directory(task_id)

    # Save task metadata. Overwrite the (optional) inbound task_id with the
    # validated server-side value so downstream consumers always see the
    # canonical id.
    task_meta = task.model_dump()
    task_meta["task_id"] = task_id
    task_meta["status"] = TaskStatus.PENDING.value
    task_meta["created_at"] = datetime.utcnow().isoformat()
    task_meta["runtime_estimate"] = _runtime_estimate_response(task_meta)
    task_meta.update(_premade_index_summary(task_meta.get("premade_index")))

    meta_file = config.TASKS_DIR / f"{task_id}.json"
    meta_file.parent.mkdir(parents=True, exist_ok=True)
    meta_file.write_text(json.dumps(task_meta, indent=2))

    # Build result link
    result_link = f"{config.NGINX_LINK}{task_id}.zip" if config.NGINX_LINK else None

    # Submit to Celery (import here to avoid circular dependency)
    from ...worker.tasks.pmet import run_pmet_task
    run_pmet_task.delay(task_meta, str(task_dir))

    return TaskResponse(
        task_id=task_id,
        status=TaskStatus.PENDING,
        mode=task.mode,
        email=task.email,
        result_link=result_link,
        created_at=datetime.utcnow(),
        runtime_estimate=task_meta.get("runtime_estimate"),
        indexing_species=task_meta.get("indexing_species"),
        indexing_motif_db=task_meta.get("indexing_motif_db"),
    )


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str):
    """Get task status and details"""
    task_file = config.TASKS_DIR / f"{task_id}.json"
    if not task_file.exists():
        raise HTTPException(status_code=404, detail="Task not found")

    task_data = json.loads(task_file.read_text())

    # Auto-flip to completed if a zip exists, but only when the recorded
    # status isn't already terminal (don't paper over a cancelled / failed
    # final state with a stale zip from a previous run).
    result_zip = config.RESULT_DIR / f"{task_id}.zip"
    current_status = task_data.get("status")
    if result_zip.exists() and current_status not in ("cancelled", "failed"):
        task_data["status"] = TaskStatus.COMPLETED.value
        task_data["completed_at"] = datetime.fromtimestamp(
            result_zip.stat().st_mtime
        ).isoformat()

    # Synthesize the public link if the worker hasn't persisted one yet
    # (older JSONs, or in-flight tasks) but the zip + nginx base exist.
    result_link = task_data.get("result_link")
    if not result_link and config.NGINX_LINK and result_zip.exists():
        result_link = f"{config.NGINX_LINK.rstrip('/')}/{task_id}.zip"

    # Surface the zip size whenever it's on disk so the UI can label the
    # download button "(123 MB)". Symmetric with partial_result_size_bytes
    # below — same UX courtesy across success and partial-failure paths.
    result_size_bytes: Optional[int] = None
    if result_zip.exists():
        try:
            result_size_bytes = result_zip.stat().st_size
        except OSError:
            result_size_bytes = None

    runtime_estimate = task_data.get("runtime_estimate")
    if not runtime_estimate:
        runtime_estimate = _runtime_estimate_response(task_data)
    index_summary = _premade_index_summary(task_data.get("premade_index"))

    # Partial-result rescue: a task that crashed in the heatmap or zip
    # step would normally be marked failed with no download surface,
    # even though pairing wrote motif_output.txt. Expose a separate
    # link in that case so the user can still grab the scientific
    # payload. Status stays 'failed' so the failure remains visible.
    partial_result_link: Optional[str] = None
    partial_result_size_bytes: Optional[int] = None
    if task_data.get("status") == "failed":
        partial_motif_output = _locate_motif_output(task_id)
        if partial_motif_output is not None:
            partial_result_link = f"/api/tasks/{task_id}/partial-result"
            try:
                partial_result_size_bytes = partial_motif_output.stat().st_size
            except OSError:
                # File vanished between locate() and stat() — treat as no
                # partial result (link without size would mislead the UI).
                partial_result_link = None

    # Per-stage view + warnings derived from on-disk artifacts. Pure
    # FS inspection — does not mutate task_data.
    stages = infer_stages(task_data, config.RESULT_DIR / task_id)
    warnings = derive_warnings(stages)
    effective_status = derive_effective_status(task_data.get("status", "pending"), stages)

    return TaskResponse(
        task_id=task_data["task_id"],
        status=TaskStatus(task_data.get("status", "pending")),
        mode=TaskMode(task_data["mode"]),
        email=task_data["email"],
        result_link=result_link,
        result_size_bytes=result_size_bytes,
        partial_result_link=partial_result_link,
        partial_result_size_bytes=partial_result_size_bytes,
        stages=stages,
        warnings=warnings if warnings else None,
        effective_status=effective_status,
        created_at=datetime.fromisoformat(task_data["created_at"]),
        started_at=datetime.fromisoformat(task_data["started_at"]) if task_data.get("started_at") else None,
        completed_at=datetime.fromisoformat(task_data["completed_at"]) if task_data.get("completed_at") else None,
        error_message=task_data.get("error_message"),
        ic_threshold=task_data.get("ic_threshold"),
        max_match=task_data.get("max_match"),
        promoter_num=task_data.get("promoter_num"),
        fimo_threshold=task_data.get("fimo_threshold"),
        promoter_length=task_data.get("promoter_length"),
        utr5=task_data.get("utr5"),
        promoters_overlap=task_data.get("promoters_overlap"),
        genes_file=task_data.get("genes_file"),
        fasta_file=task_data.get("fasta_file"),
        gff3_file=task_data.get("gff3_file"),
        meme_file=task_data.get("meme_file"),
        premade_index=task_data.get("premade_index"),
        indexing_species=task_data.get("indexing_species") or index_summary.get("indexing_species"),
        indexing_motif_db=task_data.get("indexing_motif_db") or index_summary.get("indexing_motif_db"),
        runtime_estimate=runtime_estimate,
        ncpu=config.NCPU,
    )


@router.get("/{task_id}/result")
async def download_result(task_id: str):
    """Download task result as zip file"""
    result_zip = config.RESULT_DIR / f"{task_id}.zip"
    if not result_zip.exists():
        raise HTTPException(status_code=404, detail="Result not found")
    return FileResponse(result_zip, media_type="application/zip", filename=f"{task_id}.zip")


@router.get("/{task_id}/partial-result")
async def download_partial_result(task_id: str):
    """Download motif_output.txt directly when the task was marked failed
    but the pairing stage finished. Companion to the partial_result_link
    field surfaced by GET /tasks/{id}. The task must be a known one (its
    JSON exists); we do not check status — by the time the link reaches
    the user, get_task already gated on status==failed."""
    task_file = config.TASKS_DIR / f"{task_id}.json"
    if not task_file.exists():
        raise HTTPException(status_code=404, detail="Task not found")
    motif_output = _locate_motif_output(task_id)
    if motif_output is None:
        raise HTTPException(status_code=404, detail="Partial result not available")
    # Force download instead of inline rendering — text/tab-separated-values
    # would otherwise be opened in-browser by some Chrome versions, ignoring
    # Content-Disposition. application/octet-stream is opaque so the browser
    # always falls back to "save as".
    response = FileResponse(
        motif_output,
        media_type="application/octet-stream",
        filename=f"{task_id}_motif_output.txt",
    )
    # Tell nginx not to buffer this response. The default proxy_buffering
    # would have nginx absorb the whole stream before forwarding — fine for
    # KB-MB JSON, ruinous for the GB-scale motif_output.txt that big-library
    # × many-cluster runs can produce.
    response.headers["X-Accel-Buffering"] = "no"
    return response


@router.get("", response_model=TaskListResponse)
async def list_tasks(email: str = None, task_id: str = None, limit: int = 50, offset: int = 0):
    """List tasks. Filter by exact email match, by task_id substring, or both."""
    tasks = []
    for task_file in sorted(config.TASKS_DIR.glob("*.json"), reverse=True)[offset:offset+limit]:
        task_data = json.loads(task_file.read_text())
        if email and task_data.get("email") != email:
            continue
        if task_id and task_id not in task_data.get("task_id", ""):
            continue

        status = TaskStatus(task_data.get("status", "pending"))
        result_zip = config.RESULT_DIR / f"{task_data['task_id']}.zip"
        if result_zip.exists() and status not in (TaskStatus.CANCELLED, TaskStatus.FAILED):
            status = TaskStatus.COMPLETED

        # Mirror the size field that GET /tasks/{id} surfaces — list view's
        # TaskCard reads it to label the success download "(123 MB)".
        result_size_bytes: Optional[int] = None
        if result_zip.exists():
            try:
                result_size_bytes = result_zip.stat().st_size
            except OSError:
                result_size_bytes = None

        tasks.append(TaskResponse(
            task_id=task_data["task_id"],
            status=status,
            mode=TaskMode(task_data["mode"]),
            email=task_data["email"],
            result_link=task_data.get("result_link"),
            result_size_bytes=result_size_bytes,
            created_at=datetime.fromisoformat(task_data["created_at"]),
            started_at=datetime.fromisoformat(task_data["started_at"]) if task_data.get("started_at") else None,
            completed_at=datetime.fromisoformat(task_data["completed_at"]) if task_data.get("completed_at") else None,
            error_message=task_data.get("error_message"),
        ))

    return TaskListResponse(tasks=tasks, total=len(tasks))


@router.get("/{task_id}/progress")
async def get_task_progress(task_id: str):
    """Return the live progress.json the worker writes via
    scripts/lib/progress.sh. Returns {"running": false} when the file is
    absent (task not started yet, already finished, or never instrumented).

    Defensive: if the task JSON says completed/failed/cancelled we return
    not-running regardless of file presence — covers the case where the
    executor's cleanup didn't run (worker SIGKILLed mid-write) and a
    stale progress.json would otherwise make the UI show a phantom
    progress bar.
    """
    task_file = config.TASKS_DIR / f"{task_id}.json"
    if task_file.exists():
        try:
            task_data = json.loads(task_file.read_text())
            if task_data.get("status") in ("completed", "failed", "cancelled"):
                return {"running": False}
        except (json.JSONDecodeError, OSError):
            pass

    progress_file = config.RESULT_DIR / task_id / "progress.json"
    if not progress_file.exists():
        return {"running": False}
    try:
        data = json.loads(progress_file.read_text())
        if not isinstance(data, dict):
            return {"running": False}
        data["running"] = True
        return data
    except (json.JSONDecodeError, OSError):
        return {"running": False}


@router.post("/estimate")
async def estimate_task(payload: EstimatePayload):
    """Predict task runtime from input metadata. Returns a range
    [estimate, 2 × estimate]; the upper bound is the conservative figure
    the UI surfaces. The backend reads file paths to fill in motif /
    gene / fasta-size counts if the caller didn't precompute them.
    """
    return _runtime_estimate_response(payload.model_dump())


@router.post("/{task_id}/cancel", dependencies=[Depends(require_admin)])
async def cancel_task(task_id: str, payload: CancelPayload):
    """Admin-only: terminate a running task.

    Order of operations matters here. We *first* mark the task as cancelled
    in the JSON, then kill the worker's subprocess tree. The worker's
    exception handler reads the JSON when its subprocess dies and skips
    overwriting the status if it sees "cancelled" — so the cancellation
    state is sticky and not clobbered by a "subprocess exited non-zero"
    failure path.
    """
    task_file = config.TASKS_DIR / f"{task_id}.json"
    if not task_file.exists():
        raise HTTPException(status_code=404, detail="Task not found")

    task_data = json.loads(task_file.read_text())
    current = task_data.get("status")
    if current in ("completed", "failed", "cancelled"):
        raise HTTPException(
            status_code=409,
            detail=f"Task is already {current} and cannot be cancelled",
        )

    reason = (payload.reason or "").strip()
    now = datetime.utcnow().isoformat()
    task_data["status"] = TaskStatus.CANCELLED.value
    task_data["completed_at"] = now
    task_data["cancelled_at"] = now
    task_data["cancelled_by"] = "admin"
    if reason:
        task_data["cancel_reason"] = reason
    task_file.write_text(json.dumps(task_data, indent=2))

    # Kill the worker's process tree. The PID file is written by the
    # executor at start; absent if the task hasn't reached subprocess yet
    # (still queued in celery), in which case there's nothing to kill —
    # the JSON status is enough to keep it from running when picked up.
    pid_file = config.RESULT_DIR / task_id / "worker.pid"
    killed: list[int] = []
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
        except (ValueError, OSError):
            pid = 0
        if pid:
            try:
                killed = _kill_process_tree(pid)
            except Exception:
                # Don't let psutil hiccups block the cancel response —
                # status is already written, user will get the email.
                pass

    # Email the user. Best-effort; SMTP failures shouldn't fail the API.
    try:
        MailService().send_cancelled_notification(
            task_data["email"], task_id, reason or None, task_data
        )
    except Exception:
        pass

    return {"ok": True, "killed_pids": killed, "task_id": task_id}
