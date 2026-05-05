import hmac
import re
import secrets
import time
from threading import Lock
from typing import Optional


# A "session" is a transient binding between a session_id (the directory
# under RESULT_DIR/<session_id>/upload/ that holds the files for one
# pending submission) and a server-issued secret token. It lets the task
# creation path prove that the caller owns the upload root it is about to
# submit.
UPLOAD_SESSION_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
SESSION_TTL_SECONDS = 60 * 60
SESSION_UPLOAD_MAX_BYTES = 5 * 1024 * 1024 * 1024
SESSION_UPLOAD_MAX_FILES = 8

_SESSIONS: dict[str, dict] = {}
_SESSIONS_LOCK = Lock()


def _valid_record_locked(session_id: Optional[str], token: Optional[str], now: float) -> Optional[dict]:
    """Return the session record for a valid token. Caller must hold the lock."""
    if not session_id or not token:
        return None
    record = _SESSIONS.get(session_id)
    if not record:
        return None
    if record["expires_at"] < now:
        _SESSIONS.pop(session_id, None)
        return None
    if not hmac.compare_digest(record["token"], token):
        return None
    return record


def purge_expired_sessions() -> None:
    now = time.time()
    with _SESSIONS_LOCK:
        for sid in [k for k, v in _SESSIONS.items() if v["expires_at"] < now]:
            _SESSIONS.pop(sid, None)


def validate_upload_session(session_id: Optional[str], token: Optional[str]) -> bool:
    now = time.time()
    with _SESSIONS_LOCK:
        return _valid_record_locked(session_id, token, now) is not None


def consume_upload_session(session_id: Optional[str], token: Optional[str]) -> bool:
    """Validate and remove a session token in one locked operation."""
    now = time.time()
    with _SESSIONS_LOCK:
        if _valid_record_locked(session_id, token, now) is None:
            return False
        _SESSIONS.pop(session_id, None)
        return True


def issue_upload_session() -> dict:
    purge_expired_sessions()
    for _ in range(5):
        session_id = f"pmet_{secrets.token_hex(6)}"
        with _SESSIONS_LOCK:
            if session_id not in _SESSIONS:
                token = secrets.token_hex(32)
                _SESSIONS[session_id] = {
                    "token": token,
                    "expires_at": time.time() + SESSION_TTL_SECONDS,
                    "uploaded_bytes": 0,
                    "uploaded_files": 0,
                }
                return {
                    "session_id": session_id,
                    "session_token": token,
                    "expires_in": SESSION_TTL_SECONDS,
                }
    raise RuntimeError("Could not allocate session id")


def record_session_upload(session_id: Optional[str], token: Optional[str], byte_count: int) -> bool:
    """Validate token and debit this session's upload quota atomically."""
    if byte_count < 0:
        return False
    now = time.time()
    with _SESSIONS_LOCK:
        record = _valid_record_locked(session_id, token, now)
        if not record:
            return False

        next_files = int(record.get("uploaded_files", 0)) + 1
        next_bytes = int(record.get("uploaded_bytes", 0)) + byte_count
        if next_files > SESSION_UPLOAD_MAX_FILES or next_bytes > SESSION_UPLOAD_MAX_BYTES:
            return False

        record["uploaded_files"] = next_files
        record["uploaded_bytes"] = next_bytes
        return True


def release_session_upload(session_id: Optional[str], token: Optional[str], byte_count: int) -> None:
    """Best-effort quota refund when a pre-submit uploaded file is deleted."""
    if byte_count <= 0:
        return
    now = time.time()
    with _SESSIONS_LOCK:
        record = _valid_record_locked(session_id, token, now)
        if not record:
            return
        record["uploaded_files"] = max(0, int(record.get("uploaded_files", 0)) - 1)
        record["uploaded_bytes"] = max(0, int(record.get("uploaded_bytes", 0)) - byte_count)
