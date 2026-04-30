import subprocess
import json
import os
from pathlib import Path
from datetime import datetime

from celery import shared_task

from ..celery_app import celery_app
from ...config import config
from ...services.executor import PMETExecutor
from ...services.mail import MailService
from ...services.storage import StorageService

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

        # Notify admin + user that task has started. The admin half is
        # gated by data/configure/admin_settings.json::notify_on_submit
        # so the admin can mute "New Task Submitted" without a redeploy.
        if self.request.retries == 0:
            config.reload()
            if config.NOTIFY_ON_SUBMIT:
                mail.send_admin_notification(task_meta["email"], task_meta)
            mail.send_started_notification(task_meta["email"], task_id)

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

            # Send result email
            mail.send_result_notification(task_meta["email"], result_link)
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

        return {"success": False, "error": str(e)}

    return {"success": True, "task_id": task_id}
