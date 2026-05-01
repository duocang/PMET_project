import subprocess
import json
import os
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse

from celery import shared_task

from ..celery_app import celery_app
from ...config import config
from ...services.executor import PMETExecutor
from ...services.mail import MailService
from ...services.storage import StorageService
from ...services.stage_status import (
    derive_effective_status,
    derive_warnings,
    infer_stages,
)

NON_RETRYABLE_ERROR_SNIPPETS = (
    "cannot run inside the Linux Docker worker",
    "cannot execute binary file",
    "Exec format error",
    "Script not found",
    "Required PMET binary is missing",
    "targets Linux/",
)


def is_retryable_task_error(message: str) -> bool:
    return not any(snippet in message for snippet in NON_RETRYABLE_ERROR_SNIPPETS)


def _build_partial_result_link(task_id: str) -> str:
    """Public URL for /api/tasks/<id>/partial-result, derived from
    NGINX_LINK. NGINX_LINK is the result-zip base (e.g.
    https://pmet.online/results/) — strip its path to get the host
    root, then append the API path. Empty when NGINX_LINK is unset."""
    base = (config.NGINX_LINK or "").strip()
    if not base:
        return ""
    parsed = urlparse(base)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}/api/tasks/{task_id}/partial-result"


def _summarize_error(msg: str) -> str:
    """Pick a single user-facing line out of a verbose worker error.
    Mirrors the frontend summarizeError heuristic so the email body
    leads with the same line the UI shows in its collapsed banner."""
    if not msg:
        return ""
    lines = [ln.strip() for ln in msg.splitlines() if ln.strip()]
    for ln in lines:
        if ln.lower().startswith("error"):
            return ln if len(ln) <= 200 else ln[:197] + "…"
    for ln in lines:
        if ln.startswith("!"):
            return ln if len(ln) <= 200 else ln[:197] + "…"
    for ln in lines:
        if ln.lower().startswith("command failed"):
            return ln if len(ln) <= 200 else ln[:197] + "…"
    pick = lines[0] if lines else msg
    return pick if len(pick) <= 200 else pick[:197] + "…"


def _log_runtime_history(task_meta: dict) -> None:
    """Append one JSON line to data/app/runtime_history.jsonl with the
    features needed to fit a future empirical runtime model. Best-effort —
    failure here must not block result delivery to the user.
    """
    try:
        from datetime import datetime as _dt

        history_path = config.PROJECT_ROOT / "data" / "app" / "runtime_history.jsonl"
        history_path.parent.mkdir(parents=True, exist_ok=True)

        started = task_meta.get("started_at")
        completed = task_meta.get("completed_at")
        duration_s = None
        if started and completed:
            try:
                duration_s = (
                    _dt.fromisoformat(completed) - _dt.fromisoformat(started)
                ).total_seconds()
            except ValueError:
                pass

        # File-based features. The worker's PROJECT_ROOT === host repo root
        # via bind-mount, and the file paths in task_meta are relative to it.
        n_motifs = None
        if task_meta.get("meme_file"):
            p = config.PROJECT_ROOT / task_meta["meme_file"]
            if p.exists():
                n_motifs = sum(
                    1 for line in p.read_text(errors="replace").splitlines()
                    if line.startswith("MOTIF ")
                )

        fasta_size = None
        if task_meta.get("fasta_file"):
            p = config.PROJECT_ROOT / task_meta["fasta_file"]
            if p.exists():
                fasta_size = p.stat().st_size

        n_target_genes = None
        if task_meta.get("genes_file"):
            p = config.PROJECT_ROOT / task_meta["genes_file"]
            if p.exists():
                n_target_genes = sum(
                    1 for line in p.read_text(errors="replace").splitlines()
                    if line.strip()
                )

        record = {
            "task_id": task_meta.get("task_id"),
            "mode": task_meta.get("mode"),
            "duration_s": duration_s,
            "n_motifs": n_motifs,
            "fasta_size_bytes": fasta_size,
            "n_target_genes": n_target_genes,
            "ncpu": config.NCPU,
            "ic_threshold": task_meta.get("ic_threshold"),
            "max_match": task_meta.get("max_match"),
            "promoter_num": task_meta.get("promoter_num"),
            "completed_at": completed,
        }
        with history_path.open("a") as fh:
            fh.write(json.dumps(record) + "\n")
    except Exception:
        # Best-effort — never let logging take down a task completion.
        pass


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def run_pmet_task(self, task_meta: dict, task_dir: str):
    """Execute PMET task asynchronously"""
    task_id = task_meta["task_id"]
    mode = task_meta["mode"]

    executor = PMETExecutor()
    storage = StorageService()
    mail = MailService()

    task_file = config.TASKS_DIR / f"{task_id}.json"

    try:
        preflight_error = executor.preflight_check(task_meta)
        if preflight_error:
            raise Exception(preflight_error)

        # Update status to running
        task_meta["status"] = "running"
        task_meta["started_at"] = datetime.utcnow().isoformat()
        task_file.write_text(json.dumps(task_meta, indent=2))

        # Notify admin + user that task has started. Both switches are
        # hot-reloaded from data/configure/admin_settings.json.
        if self.request.retries == 0:
            config.reload()
            if config.NOTIFY_ON_SUBMIT:
                mail.send_admin_notification(task_meta["email"], task_meta)
            if config.NOTIFY_USER_ON_START:
                mail.send_started_notification(task_meta["email"], task_meta)

        # Build and execute PMET command
        result = executor.execute(task_meta)

        if result["success"]:
            # If the cancel API beat us to it (rare but possible: cancel
            # arrives just as the subprocess exits cleanly), respect that
            # and don't overwrite the terminal state with "completed".
            if task_file.exists():
                try:
                    current = json.loads(task_file.read_text())
                    if current.get("status") == "cancelled":
                        return {"success": False, "error": "cancelled"}
                except json.JSONDecodeError:
                    pass

            # Zip results
            result_dir = Path(task_dir)
            storage.zip_results(result_dir, task_id)

            # Build the public download link from the configured nginx base
            # (data/configure/nginx_link.txt) and persist it to task_meta so
            # both the email and later GET /tasks/{id} return the same URL.
            base = config.NGINX_LINK.rstrip("/")
            result_link = f"{base}/{task_id}.zip" if base else ""

            # Update status to completed
            task_meta["status"] = "completed"
            task_meta["completed_at"] = datetime.utcnow().isoformat()
            task_meta["result_link"] = result_link
            task_file.write_text(json.dumps(task_meta, indent=2))

            # Append a runtime-history record. Static estimator (Plan A)
            # doesn't read this yet — it's accumulating fuel for the empirical
            # estimator (Plan B) we may slot in later. ~200 bytes per record,
            # safe to keep forever.
            _log_runtime_history(task_meta)

            # Send result email — include any non-fatal warnings derived
            # from the on-disk artifacts (e.g. heatmap was skipped). Empty
            # list passes through untouched, preserving the legacy mail
            # body for clean runs.
            stages = infer_stages(task_meta, config.RESULT_DIR / task_id)
            warnings = derive_warnings(stages)
            mail.send_result_notification(
                task_meta["email"], result_link, task_meta, warnings=warnings
            )
        else:
            raise Exception(result.get("error", "PMET execution failed"))

    except Exception as e:
        # The cancel endpoint marks status=cancelled BEFORE killing the
        # subprocess. If we re-read the file and find that already, don't
        # overwrite to "failed" — the cancellation path owns the final
        # state and has already emailed the user.
        if task_file.exists():
            try:
                current = json.loads(task_file.read_text())
                if current.get("status") == "cancelled":
                    return {"success": False, "error": "cancelled"}
            except json.JSONDecodeError:
                pass

        task_meta["status"] = "failed"
        task_meta["error_message"] = str(e)
        task_meta["completed_at"] = datetime.utcnow().isoformat()
        task_file.write_text(json.dumps(task_meta, indent=2))

        # Retry logic
        if self.request.retries < self.max_retries and is_retryable_task_error(str(e)):
            raise self.retry(exc=e)

        # Final failure — branch by recoverability. If the pairing stage
        # produced motif_output.txt despite the late-stage crash, mail
        # the user a partial-result link instead of a generic "failed".
        # Otherwise send the failure email with an error summary + the
        # common-causes checklist.
        try:
            stages = infer_stages(task_meta, config.RESULT_DIR / task_id)
            effective = derive_effective_status("failed", stages)
            warnings = derive_warnings(stages)
            error_summary = _summarize_error(str(e))

            if effective == "partial_success":
                partial_link = _build_partial_result_link(task_id)
                mail.send_partial_result_notification(
                    task_meta["email"],
                    partial_link,
                    error_summary,
                    warnings,
                    task_meta,
                )
            else:
                mail.send_failed_notification(
                    task_meta["email"], error_summary, task_meta
                )
        except Exception as mail_err:
            # Never let a mail failure mask the original exception path.
            print(f"failure-notification dispatch error: {mail_err}", flush=True)

        return {"success": False, "error": str(e)}

    return {"success": True, "task_id": task_id}
