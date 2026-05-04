import gzip
import hmac
import json
import os
import re
import secrets
import shutil
import time
from pathlib import Path
from threading import Lock
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request

from ...config import config

router = APIRouter(prefix="/files", tags=["files"])


# ─── Session token store ──────────────────────────────────────────────
# A "session" is a transient binding between a session_id (the directory
# under RESULT_DIR/<session_id>/upload/ that holds the files for one
# pending submission) and a server-issued secret token. Required for
# /use-example and DELETE /upload so an unauthenticated public caller
# can't (a) make the server `cp` 100+ MB demo files for free
# (#12, the "disk amplifier" issue) or (b) delete another session's
# upload by guessing the path (#14).
#
# In-memory module-level state is fine for the dev/single-worker layout.
# Multi-worker prod would want redis here; the API surface stays the
# same and only `_validate_session` / `_issue_session` change.
_SESSIONS: dict[str, dict] = {}
_SESSIONS_LOCK = Lock()
_SESSION_TTL_SECONDS = 60 * 60  # 1 h is more than enough to fill the form

# Per-IP rate limit on issue-session so a bot can't farm millions of
# tokens to drive the use-example endpoint. Sliding window via a deque
# of timestamps per IP. _ISSUE_RATE_LIMIT requests per
# _ISSUE_RATE_WINDOW_SECONDS are allowed.
_ISSUE_RATE_LIMIT = 10
_ISSUE_RATE_WINDOW_SECONDS = 60
_RATE_BUCKETS: dict[str, list[float]] = {}
_RATE_LOCK = Lock()


def _purge_expired_sessions() -> None:
    """Drop expired session records. Cheap O(N) sweep — N is the number
    of in-flight forms (typically < 100), called only when a new session
    is issued or validated, not per file op."""
    now = time.time()
    with _SESSIONS_LOCK:
        for sid in [k for k, v in _SESSIONS.items() if v["expires_at"] < now]:
            _SESSIONS.pop(sid, None)


def _validate_session(session_id: Optional[str], token: Optional[str]) -> bool:
    """Constant-time check that ``token`` matches the secret we issued
    for ``session_id`` and the session hasn't aged out."""
    if not session_id or not token:
        return False
    now = time.time()
    with _SESSIONS_LOCK:
        record = _SESSIONS.get(session_id)
        if not record:
            return False
        if record["expires_at"] < now:
            _SESSIONS.pop(session_id, None)
            return False
        return hmac.compare_digest(record["token"], token)


def _check_issue_rate_limit(ip: str) -> bool:
    """Sliding window: at most _ISSUE_RATE_LIMIT issue-session calls
    per _ISSUE_RATE_WINDOW_SECONDS from the same IP. Returns True when
    the request fits inside the window, False once the cap is hit."""
    now = time.time()
    cutoff = now - _ISSUE_RATE_WINDOW_SECONDS
    with _RATE_LOCK:
        bucket = _RATE_BUCKETS.setdefault(ip, [])
        # Trim old entries in place.
        bucket[:] = [t for t in bucket if t >= cutoff]
        if len(bucket) >= _ISSUE_RATE_LIMIT:
            return False
        bucket.append(now)
        return True

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


@router.post("/issue-session")
async def issue_session(request: Request):
    """Hand the caller a fresh ``(session_id, session_token)`` pair.

    The frontend calls this once on /submit page mount and uses the pair
    for every subsequent upload / use-example / delete-upload during the
    same form session. Server keeps the token in a rolling in-memory
    map for ``_SESSION_TTL_SECONDS``; calls without a valid token are
    rejected on use-example and DELETE.

    IP-rate-limited so a hostile client can't farm tokens fast enough to
    drive use-example into a disk-amplification DoS.
    """
    ip = request.client.host if request.client else "unknown"
    if not _check_issue_rate_limit(ip):
        raise HTTPException(
            status_code=429,
            detail=f"Too many session requests from {ip}; try again in a minute",
        )
    _purge_expired_sessions()

    # 12 hex chars (48-bit entropy) keeps URLs short and matches the
    # legacy frontend-side generator that this replaces. Retry on the
    # astronomically unlikely collision.
    for _ in range(5):
        session_id = f"pmet_{secrets.token_hex(6)}"
        with _SESSIONS_LOCK:
            if session_id not in _SESSIONS:
                token = secrets.token_hex(32)  # 64 hex chars, 256-bit
                _SESSIONS[session_id] = {
                    "token": token,
                    "expires_at": time.time() + _SESSION_TTL_SECONDS,
                }
                break
    else:
        raise HTTPException(status_code=500, detail="Could not allocate session id")
    return {
        "session_id": session_id,
        "session_token": token,
        "expires_in": _SESSION_TTL_SECONDS,
    }


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    task_id: Optional[str] = Form(None),
    file_type: str = Form(...),  # genes, fasta, gff3, meme
):
    """Upload a file for PMET analysis.

    Note: not gated by session_token — attackers uploading their own
    files would still have to pay their own bandwidth, and the more
    serious "server-side amplifier" path is /use-example, which is
    gated below. Keeping /upload open also preserves backwards
    compatibility with any non-form caller during the rollout.
    """
    return _save_uploaded_file(file, task_id, file_type)


@router.post("/use-example")
async def use_example_file(
    task_id: str = Form(...),
    mode: str = Form(...),
    slot: str = Form(...),
    session_token: str = Form(...),
):
    """Server-side copy of a demo file into the user's upload dir.

    Skips the wasteful "browser fetches 116 MB FASTA, then re-uploads
    the same 116 MB" round-trip that the client-side Use Example flow
    used to do. Gated by session_token (issued via /issue-session) —
    without that gate any anonymous caller could make the server `cp`
    100+ MB demo files for free, a textbook disk-amplification DoS.

    Idempotent: if a demo file with the same target name + size is
    already in the user's upload dir, we skip the second copy. Stops a
    legitimate user double-clicking "Use example" from doubling disk
    cost, and trims attacker amplification gain to a single ~120 MB cap
    per token.
    """
    # Imported lazily so the route module doesn't pull demo's table on
    # every cold start; demo.py has no side effects but the indirection
    # keeps the boundaries clean.
    from .demo import DEMO_FILES

    _validate_session_id(task_id)
    if not _validate_session(task_id, session_token):
        raise HTTPException(status_code=401, detail="Invalid or expired session token")
    entry = DEMO_FILES.get((mode, slot))
    if not entry:
        raise HTTPException(status_code=404, detail=f"No demo file for ({mode}, {slot})")
    rel_src, public_name = entry
    src = config.PROJECT_ROOT / "data" / rel_src
    if not src.exists():
        raise HTTPException(status_code=404, detail="Demo file missing on server")

    upload_dir = _resolve_upload_dir(task_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / public_name

    src_size = src.stat().st_size
    # Path.exists() / Path.stat() follow symlinks by default — the
    # second-call dedup check transparently handles a previous symlink
    # too (size resolves to target size).
    if dest.exists() and dest.stat().st_size == src_size:
        return {
            "filename": public_name,
            "path": str(dest.relative_to(config.PROJECT_ROOT)),
            "size": src_size,
            "deduplicated": True,
        }

    # Symlink instead of copy. The demo files (TAIR10 116 MB FASTA,
    # 105 MB GFF3, motif libraries) are read-only server assets the
    # workflow scripts only consume — no point spending the disk + I/O
    # to duplicate them per session. Hard link would be cheaper still
    # but docker bind-mounts /app/data and /app/results as separate
    # devices ("Invalid cross-device link"), so symlink is the
    # portable choice. os.symlink takes the absolute target path so it
    # resolves identically in the api and worker containers (both
    # mount /app/data at the same path). Fallback to copy if the
    # platform doesn't support symlink at all (unusual — Windows
    # without privileges might).
    src_abs = src.resolve()
    try:
        os.symlink(src_abs, dest)
    except (OSError, NotImplementedError) as link_exc:
        try:
            shutil.copy2(src, dest)
        except OSError as copy_exc:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to install demo file (symlink: {link_exc}; copy: {copy_exc})",
            ) from copy_exc
    return {
        "filename": public_name,
        "path": str(dest.relative_to(config.PROJECT_ROOT)),
        "size": dest.stat().st_size,
    }


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
async def delete_upload(path: str, session_token: Optional[str] = None):
    """Delete a file the user previously uploaded.

    Strict scope: ``path`` must resolve to
    ``RESULT_DIR/<upload_session_id>/upload/<filename>`` exactly. The
    session_token must be the one we issued for that session_id. The
    earlier revision only enforced the path shape, which let any
    caller who knew (or guessed) a session_id delete that session's
    files — fine on a closed VPN, not fine on a public domain.
    """
    result_root = config.RESULT_DIR.resolve()
    # NOTE: do *not* resolve() the target — when use-example installs
    # a demo file as a symlink (the cheap path), Path.resolve() would
    # follow it back to /app/data/<demo>, which then fails the
    # relative_to(RESULT_DIR) containment check and returns a
    # confusing "outside the upload area" error. os.path.normpath
    # collapses ../ traversal without dereferencing symlinks, which
    # is exactly the safety property we need here.
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
    if not _validate_session(parts[0], session_token):
        raise HTTPException(status_code=401, detail="Invalid or expired session token")
    try:
        target.unlink()
    except FileNotFoundError:
        # Idempotent: race between TOCTOU exists() check and the unlink
        # used to return 404, which surprised callers retrying after a
        # successful previous delete. Treat "already gone" as success.
        return {"deleted": path, "noop": True}
    except IsADirectoryError as exc:
        raise HTTPException(status_code=400, detail="Target is a directory, not a file") from exc
    return {"deleted": path}
