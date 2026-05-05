import gzip
import json
import os
import re
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Form, Header, HTTPException, Request
from starlette.datastructures import UploadFile

from ...config import config
from ..upload_sessions import (
    UPLOAD_SESSION_RE,
    issue_upload_session,
    record_session_upload,
    release_session_upload,
    validate_upload_session,
)

router = APIRouter(prefix="/files", tags=["files"])

# Maps the user-facing slot name (genes / fasta / gff3 / meme) to the
# corresponding key in the persisted task metadata. Must match the keys
# api/routes/tasks.py writes when a task is created.
_PREVIEW_SLOT_KEYS = {
    "genes": "genes_file",
    "fasta": "fasta_file",
    "gff3": "gff3_file",
    "meme": "meme_file",
}

# Hard cap on how many bytes the preview endpoint streams back. Keeps
# the response small enough to render without locking up the browser
# even when the underlying file is several hundred MB (FASTA / GFF3).
_PREVIEW_BYTE_CAP = 1 * 1024 * 1024  # 1 MiB

# Skip the line-count pass for files larger than this; on a 100 MB GFF3
# the count costs noticeable wall-clock for no real UX benefit (the UI
# only uses the count to size pagination on small line-oriented files
# like a gene list, where the file is well under this threshold).
_LINE_COUNT_MAX_BYTES = 5 * 1024 * 1024  # 5 MiB

# Hard caps on what /upload accepts. Anything exceeding either bound is
# aborted mid-stream and the partial dest file is unlinked. nginx caps
# the request body at 1 GB before we even see it; these app-level caps
# additionally guard the gzip decompression path against a "10 KB gzip →
# 10 GB plaintext" zip-bomb. Sized to cover medium-large plant genomes
# (rice ~370 MB plain, maize ~2.5 GB plain via gzip) — wheat / human
# genome scale should not be analysed via the web upload path.
_UPLOAD_MAX_BYTES = 1024 * 1024 * 1024           # 1 GB raw / on-the-wire
_DECOMPRESSED_MAX_BYTES = 5 * 1024 * 1024 * 1024  # 5 GB gzip output
_UPLOAD_CHUNK_BYTES = 1 * 1024 * 1024            # 1 MiB per loop iteration

ALLOWED_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "genes": (".txt", ".tsv"),
    "fasta": (".fa", ".fasta", ".fa.gz", ".fasta.gz"),
    "gff3": (".gff", ".gff3", ".gff.gz", ".gff3.gz"),
    "meme": (".meme",),
}

GZIP_ENABLED_FILE_TYPES = {"fasta", "gff3"}


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


def _resolve_upload_dir(task_id: str) -> Path:
    """Pick the destination directory for an upload.

    With a task_id (the frontend generates a UUID on submit-page mount and
    reuses it for every upload + the eventual POST /tasks), all files for
    that task land in results/app/<task_id>/upload/, alongside indexing/ and
    pairing/ that the run will populate.
    """
    return config.RESULT_DIR / _validate_session_id(task_id) / "upload"


def _sanitize_filename(filename: str, fallback: str = "upload") -> str:
    base = Path(filename).name
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._-")
    return safe or fallback


def _open_upload_destination(destination: Path):
    """Open an upload target without following a stale symlink.

    Older /use-example revisions placed symlinks under upload/. If a user
    later uploaded a same-name file, plain open("wb") would follow the link
    and overwrite the read-only app data target. New code no longer creates
    those links, but this keeps old sessions and local dev runs safe.
    """
    if destination.is_symlink():
        destination.unlink()
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(destination, flags, 0o644)
    return os.fdopen(fd, "wb")


class _UploadTooLarge(Exception):
    """Raised mid-stream when the running byte count crosses a cap."""

    def __init__(self, kind: str, limit: int) -> None:
        super().__init__(kind)
        self.kind = kind  # "raw" or "decompressed"
        self.limit = limit


def _copy_capped(src, dest, cap: int, kind: str) -> int:
    """Stream src→dest in 1-MiB chunks, aborting once written > cap.

    Returns the total byte count on success. On overflow it stops writing
    immediately, raises _UploadTooLarge, and lets the caller unlink the
    partial dest. We avoid shutil.copyfileobj because it has no built-in
    way to enforce a running cap, which is exactly the gzip-bomb gap
    we're closing.
    """
    written = 0
    while True:
        chunk = src.read(_UPLOAD_CHUNK_BYTES)
        if not chunk:
            return written
        written += len(chunk)
        if written > cap:
            raise _UploadTooLarge(kind, cap)
        dest.write(chunk)


def _upload_too_large_detail(kind: str, limit: int) -> str:
    if limit >= 1024 * 1024 * 1024 and limit % (1024 * 1024 * 1024) == 0:
        size = f"{limit // (1024 * 1024 * 1024)} GB"
    else:
        size = f"{limit // (1024 * 1024)} MB"
    return (
        f"Uploaded gzip expands beyond the {size} decompressed-size cap"
        if kind == "decompressed"
        else f"Uploaded file exceeds the {size} size cap"
    )


def _spooled_upload_size(file: UploadFile) -> Optional[int]:
    """Return the multipart part size without reading it into memory."""
    size = getattr(file, "size", None)
    if isinstance(size, int) and size >= 0:
        return size
    try:
        current = file.file.tell()
        file.file.seek(0, os.SEEK_END)
        end = file.file.tell()
        file.file.seek(current)
        return end
    except (OSError, AttributeError):
        return None


def _enforce_raw_upload_cap(file: UploadFile) -> None:
    raw_size = _spooled_upload_size(file)
    if raw_size is not None and raw_size > _UPLOAD_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=_upload_too_large_detail("raw", _UPLOAD_MAX_BYTES),
        )


def _store_upload(file: UploadFile, destination: Path, decompress_gzip: bool) -> None:
    try:
        with _open_upload_destination(destination) as buffer:
            file.file.seek(0)
            if decompress_gzip:
                with gzip.GzipFile(fileobj=file.file, mode="rb") as gzipped:
                    _copy_capped(gzipped, buffer, _DECOMPRESSED_MAX_BYTES, "decompressed")
            else:
                _copy_capped(file.file, buffer, _UPLOAD_MAX_BYTES, "raw")
    except _UploadTooLarge as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(
            status_code=413,
            detail=_upload_too_large_detail(exc.kind, exc.limit),
        ) from exc
    except (OSError, EOFError, gzip.BadGzipFile) as exc:
        destination.unlink(missing_ok=True)
        detail = (
            "Uploaded gzip file is invalid or corrupted"
            if decompress_gzip
            else f"Could not store uploaded file: {exc}"
        )
        raise HTTPException(status_code=400, detail=detail) from exc


def _save_uploaded_file(file: UploadFile, task_id: str, file_type: str) -> dict:
    _enforce_raw_upload_cap(file)

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


def _require_upload_session(session_id: Optional[str], session_token: Optional[str]) -> str:
    if not session_id:
        raise HTTPException(status_code=400, detail="Missing upload session id")
    task_id = _validate_session_id(session_id)
    if not validate_upload_session(task_id, session_token):
        raise HTTPException(status_code=401, detail="Invalid or expired session token")
    return task_id


async def _parse_upload_form(request: Request) -> tuple[UploadFile, str]:
    form = await request.form()
    file = form.get("file")
    file_type = form.get("file_type")
    if not isinstance(file, UploadFile):
        raise HTTPException(status_code=400, detail="Missing uploaded file")
    if not isinstance(file_type, str) or not file_type:
        raise HTTPException(status_code=400, detail="Missing file_type")
    return file, file_type


def _record_upload_or_reject(task_id: str, session_token: Optional[str], result: dict) -> None:
    if record_session_upload(task_id, session_token, int(result.get("size") or 0)):
        return
    target = config.PROJECT_ROOT / result["path"]
    target.unlink(missing_ok=True)
    raise HTTPException(status_code=413, detail="Upload session quota exceeded")


@router.post("/issue-session")
async def issue_session():
    """Hand the caller a fresh ``(session_id, session_token)`` pair.

    The frontend calls this once on /submit page mount and uses the pair
    for every subsequent use-example / delete-upload during the same
    form session. Server keeps the token in a rolling in-memory map for
    ``SESSION_TTL_SECONDS``; calls without a valid token are rejected
    on use-example and DELETE.

    Per-IP rate limiting moved to nginx (``limit_req_zone`` against
    ``$binary_remote_addr`` in deploy/nginx/nginx.conf). nginx sees the
    real client IP at the connection level, which is more reliable than
    making the FastAPI process trust X-Forwarded-For; it also keeps the
    cap correct under multi-worker deployments where a per-process dict
    would inflate the effective rate by N.
    """
    try:
        return issue_upload_session()
    except RuntimeError:
        raise HTTPException(status_code=500, detail="Could not allocate session id")


@router.post("/upload")
async def upload_file(
    request: Request,
    session_id: Optional[str] = Header(default=None, alias="X-PMET-Session-Id"),
    session_token: Optional[str] = Header(default=None, alias="X-PMET-Session-Token"),
):
    """Upload a file for PMET analysis.

    Public-facing post-pmet.online: gated by the same session_token that
    /use-example and DELETE /upload require. The session id is a header
    instead of a form field so we can validate it before asking Starlette
    to parse the multipart body; invalid callers are rejected before large
    uploads get spooled to /tmp. Per-request raw/decompressed caps bound a
    single file, and per-session quota bounds repeated use of one token.
    """
    task_id = _require_upload_session(session_id, session_token)
    file, file_type = await _parse_upload_form(request)
    result = _save_uploaded_file(file, task_id, file_type)
    _record_upload_or_reject(task_id, session_token, result)
    return result


@router.post("/use-example")
async def use_example_file(
    task_id: str = Form(...),
    mode: str = Form(...),
    slot: str = Form(...),
    session_token: str = Form(...),
):
    """Return a read-only app demo file path for the user's task.

    Skips the wasteful "browser fetches 116 MB FASTA, then re-uploads
    the same 116 MB" round-trip that the client-side Use Example flow
    used to do. Earlier revisions installed the file into upload/ via
    copy and later symlink; the symlink avoided disk amplification but
    created a write-through hazard if a later same-name upload followed
    the link. The safer model is zero install: workflow metadata points
    straight at the immutable data/ asset, and docker mounts data/ read-only.

    Gated by session_token (issued via /issue-session) so the submit flow
    keeps one consistent server-issued session boundary.
    """
    # Imported lazily so the route module doesn't pull demo's table on
    # every cold start; demo.py has no side effects but the indirection
    # keeps the boundaries clean.
    from .demo import DEMO_FILES

    _validate_session_id(task_id)
    if not validate_upload_session(task_id, session_token):
        raise HTTPException(status_code=401, detail="Invalid or expired session token")
    entry = DEMO_FILES.get((mode, slot))
    if not entry:
        raise HTTPException(status_code=404, detail=f"No demo file for ({mode}, {slot})")
    rel_src, public_name = entry
    data_root = (config.PROJECT_ROOT / "data").resolve()
    src = (data_root / rel_src).resolve()
    try:
        src.relative_to(data_root)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="Demo file escaped data root") from exc
    if not src.is_file():
        raise HTTPException(status_code=404, detail="Demo file missing on server")
    return {
        "filename": public_name,
        "path": str(src.relative_to(config.PROJECT_ROOT)),
        "size": src.stat().st_size,
    }


@router.get("/preview/{task_id}/{slot}")
async def preview_uploaded_file(task_id: str, slot: str):
    """Serve a size-capped text preview of a user-uploaded input file.

    Strict scope: only files inside `results/app/<task_id>/upload/` are
    eligible. Server-side reference data (TAIR10 FASTA, motif libraries,
    precomputed indexes) is *not* served — the path-confinement check
    will 403 those even if a caller hand-crafts the slot. This keeps the
    endpoint from turning into a generic file reader and removes the
    risk of the path-traversal class of bugs.

    The cap (`_PREVIEW_BYTE_CAP`) is intentionally crude: read the first
    N bytes regardless of structure. For multi-MB FASTA / GFF3 inputs
    the caller renders a "showing first N MB of M MB" banner; for a
    short gene list the cap is never hit and the full file comes back.
    """
    if slot not in _PREVIEW_SLOT_KEYS:
        raise HTTPException(status_code=400, detail=f"Unknown preview slot: {slot}")

    _validate_session_id(task_id)

    task_file = config.TASKS_DIR / f"{task_id}.json"
    if not task_file.exists():
        raise HTTPException(status_code=404, detail="Task not found")
    try:
        task_data = json.loads(task_file.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise HTTPException(status_code=500, detail="Task metadata unreadable") from exc

    rel_path = task_data.get(_PREVIEW_SLOT_KEYS[slot])
    if not rel_path:
        raise HTTPException(status_code=404, detail=f"No {slot} file for this task")

    # Resolve to an absolute path, then assert it lies inside this
    # task's upload directory. realpath() on both sides defends against
    # symlink games on the filesystem (the upload area is normally
    # non-symlinked but cheap insurance is still cheap).
    target = (config.PROJECT_ROOT / rel_path).resolve()
    upload_root = (config.RESULT_DIR / task_id / "upload").resolve()
    try:
        target.relative_to(upload_root)
    except ValueError as exc:
        # Server-side reference data (TAIR10, motif libraries, precomputed
        # indexes) lives outside the upload area and is intentionally
        # excluded — the user-facing preview is for *user-uploaded* inputs.
        raise HTTPException(status_code=403, detail="File is not user-uploaded") from exc

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File missing on disk")

    size = target.stat().st_size
    truncated = size > _PREVIEW_BYTE_CAP

    with target.open("rb") as fh:
        raw = fh.read(_PREVIEW_BYTE_CAP if truncated else size)
    # decode as utf-8 — input files we accept are all text. errors='replace'
    # keeps a single bad byte from killing the whole preview.
    content = raw.decode("utf-8", errors="replace")
    if truncated:
        # Don't leave the response ending mid-line; the table renderer on
        # the frontend would otherwise show a half-row at the bottom.
        last_nl = content.rfind("\n")
        if last_nl > 0:
            content = content[:last_nl]

    line_count = None
    if size <= _LINE_COUNT_MAX_BYTES:
        with target.open("rb") as fh:
            line_count = sum(1 for _ in fh)

    return {
        "filename": target.name,
        "size_bytes": size,
        "content": content,
        "truncated": truncated,
        "line_count": line_count,
    }


@router.delete("/upload")
async def delete_upload(
    path: str,
    session_token: Optional[str] = Header(default=None, alias="X-PMET-Session-Token"),
):
    """Delete a file the user previously uploaded.

    Strict scope: ``path`` must resolve to
    ``RESULT_DIR/<upload_session_id>/upload/<filename>`` exactly. The
    X-PMET-Session-Token must be the one we issued for that session_id.
    The token is intentionally a header rather than a query parameter so
    it does not land in browser history, access logs, or referrer-like
    telemetry. The earlier revision only enforced the path shape, which
    let any caller who knew (or guessed) a session_id delete that
    session's files — fine on a closed VPN, not fine on a public domain.
    """
    result_root = config.RESULT_DIR.resolve()
    # NOTE: do *not* resolve() the target. Old use-example revisions may
    # have left upload/ symlinks behind; unlinking those should remove the
    # link itself, never follow it into data/. os.path.normpath collapses
    # ../ traversal without dereferencing symlinks.
    target = Path(os.path.normpath(config.PROJECT_ROOT / path))
    try:
        rel = target.relative_to(result_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Path is outside the upload area") from exc
    parts = rel.parts
    if len(parts) != 3 or parts[1] != "upload":
        raise HTTPException(
            status_code=400,
            detail="Path must be RESULT_DIR/<session_id>/upload/<filename>",
        )
    if not UPLOAD_SESSION_RE.match(parts[0]):
        raise HTTPException(status_code=400, detail="Invalid session id")
    if not validate_upload_session(parts[0], session_token):
        raise HTTPException(status_code=401, detail="Invalid or expired session token")
    try:
        deleted_size = target.lstat().st_size
        target.unlink()
    except FileNotFoundError:
        # Idempotent: race between TOCTOU exists() check and the unlink
        # used to return 404, which surprised callers retrying after a
        # successful previous delete. Treat "already gone" as success.
        return {"deleted": path, "noop": True}
    except IsADirectoryError as exc:
        raise HTTPException(status_code=400, detail="Target is a directory, not a file") from exc
    release_session_upload(parts[0], session_token, deleted_size)
    return {"deleted": path}
