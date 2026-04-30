import gzip
import re
import shutil
import time
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from ...config import config

router = APIRouter(prefix="/files", tags=["files"])

ALLOWED_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "genes": (".txt", ".tsv"),
    "fasta": (".fa", ".fasta", ".fa.gz", ".fasta.gz"),
    "gff3": (".gff", ".gff3", ".gff.gz", ".gff3.gz"),
    "meme": (".meme",),
}

GZIP_ENABLED_FILE_TYPES = {"fasta", "gff3"}

UPLOAD_SESSION_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


def _match_extension(filename: str, allowed_extensions: tuple[str, ...]) -> Optional[str]:
    lower_name = filename.lower()
    for extension in sorted(allowed_extensions, key=len, reverse=True):
        if lower_name.endswith(extension):
            return extension
    return None


def _validate_session_id(task_id: str) -> str:
    if not UPLOAD_SESSION_RE.match(task_id):
        raise HTTPException(status_code=400, detail="Invalid upload session id")
    return task_id


def _resolve_upload_dir(task_id: Optional[str]) -> Path:
    """Pick the destination directory for an upload.

    With a task_id (the frontend generates a UUID on submit-page mount and
    reuses it for every upload + the eventual POST /tasks), all files for
    that task land in results/app/<task_id>/upload/, alongside indexing/ and
    pairing/ that the run will populate. Without a task_id we fall back to
    a per-call temp dir for legacy clients.
    """
    if task_id:
        return config.RESULT_DIR / _validate_session_id(task_id) / "upload"

    temp_id = f"temp_{int(time.time() * 1000)}"
    return config.RESULT_DIR / temp_id


def _sanitize_filename(filename: str, fallback: str = "upload") -> str:
    base = Path(filename).name
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._-")
    return safe or fallback


def _store_upload(file: UploadFile, destination: Path, decompress_gzip: bool) -> None:
    try:
        with destination.open("wb") as buffer:
            file.file.seek(0)
            if decompress_gzip:
                with gzip.GzipFile(fileobj=file.file, mode="rb") as gzipped:
                    shutil.copyfileobj(gzipped, buffer)
            else:
                shutil.copyfileobj(file.file, buffer)
    except OSError as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Uploaded gzip file is invalid or corrupted") from exc


def _save_uploaded_file(file: UploadFile, task_id: Optional[str], file_type: str) -> dict:
    if file_type == "auto":
        upload_dir = _resolve_upload_dir(task_id)
        upload_dir.mkdir(parents=True, exist_ok=True)

        dest_name = _sanitize_filename(file.filename or "")
        dest_path = upload_dir / dest_name
        _store_upload(file, dest_path, decompress_gzip=False)
        return {
            "filename": file.filename,
            "path": str(dest_path.relative_to(config.PROJECT_ROOT)),
            "size": dest_path.stat().st_size,
        }

    allowed_extensions = ALLOWED_EXTENSIONS.get(file_type)
    if not allowed_extensions:
        raise HTTPException(status_code=400, detail=f"Unsupported file type slot: {file_type}")

    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file is missing a filename")

    matched_extension = _match_extension(file.filename, allowed_extensions)
    if not matched_extension:
        allowed_list = ", ".join(allowed_extensions)
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file extension for {file_type}. Allowed: {allowed_list}",
        )

    decompress_gzip = matched_extension.endswith(".gz")
    if decompress_gzip and file_type not in GZIP_ENABLED_FILE_TYPES:
        raise HTTPException(status_code=400, detail=f"Gzip uploads are not supported for {file_type}")

    upload_dir = _resolve_upload_dir(task_id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    dest_name = _sanitize_filename(file.filename)
    if decompress_gzip and dest_name.lower().endswith(".gz"):
        dest_name = dest_name[:-3]

    dest_path = upload_dir / dest_name
    _store_upload(file, dest_path, decompress_gzip=decompress_gzip)

    return {
        "filename": file.filename,
        "path": str(dest_path.relative_to(config.PROJECT_ROOT)),
        "size": dest_path.stat().st_size,
    }


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    task_id: Optional[str] = Form(None),
    file_type: str = Form(...),  # genes, fasta, gff3, meme
):
    """Upload a file for PMET analysis"""
    return _save_uploaded_file(file, task_id, file_type)


@router.post("/upload-multiple")
async def upload_multiple_files(
    files: list[UploadFile] = File(...),
    task_id: Optional[str] = Form(None),
):
    """Upload multiple files at once"""
    results = []
    for file in files:
        result = _save_uploaded_file(file, task_id, "auto")
        results.append(result)
    return {"files": results}


@router.delete("/upload")
async def delete_upload(path: str):
    """Delete a file the user previously uploaded.

    `path` is the project-relative path that POST /upload returned. We
    resolve it to an absolute path and refuse anything that escapes
    RESULT_DIR (defends against ../.. traversal).
    """
    result_root = config.RESULT_DIR.resolve()
    target = (config.PROJECT_ROOT / path).resolve()
    try:
        target.relative_to(result_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Path is outside the upload area") from exc
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    target.unlink()
    return {"deleted": path}
