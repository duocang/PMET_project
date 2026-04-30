import re
import zipfile
from pathlib import Path
from datetime import datetime
from typing import Optional

from ..config import config


TASK_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


class StorageService:
    """Handle file storage and task directory management"""

    def generate_task_id(self, email: str, override: Optional[str] = None) -> str:
        """Return a task id, honouring a frontend-supplied override.

        Each task lives at results/app/<task_id>/{upload,indexing,pairing}/. When
        the frontend supplies a UUID we reuse it so uploads and run output
        share one root. The override is validated against TASK_ID_RE to
        prevent path traversal.
        """
        if override and TASK_ID_RE.match(override):
            return override

        safe_email = email.replace("@", "-")
        timestamp = datetime.now().strftime("%Y%b%d_%H%M")
        return f"{safe_email}_{timestamp}"

    def create_task_directory(self, task_id: str) -> Path:
        """Create the task root and its three canonical subdirectories."""
        task_dir = config.RESULT_DIR / task_id
        for sub in ("upload", "indexing", "pairing"):
            (task_dir / sub).mkdir(parents=True, exist_ok=True)
        return task_dir

    def zip_results(self, result_dir: Path, task_id: str) -> Path:
        """Create zip file of results"""
        zip_path = config.RESULT_DIR / f"{task_id}.zip"

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for file_path in result_dir.rglob("*"):
                if file_path.is_file():
                    arcname = file_path.relative_to(result_dir)
                    zf.write(file_path, arcname)

        return zip_path
