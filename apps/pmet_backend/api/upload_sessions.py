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

_SESSIONS: dict[str, dict] = {}
_SESSIONS_LOCK = Lock()


def purge_expired_sessions() -> None:
    now = time.time()
    with _SESSIONS_LOCK:
        for sid in [k for k, v in _SESSIONS.items() if v["expires_at"] < now]:
            _SESSIONS.pop(sid, None)


def validate_upload_session(session_id: Optional[str], token: Optional[str]) -> bool:
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


def consume_upload_session(session_id: Optional[str], token: Optional[str]) -> bool:
    """Validate and remove a session token in one locked operation."""
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
        if not hmac.compare_digest(record["token"], token):
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
                }
                return {
                    "session_id": session_id,
                    "session_token": token,
                    "expires_in": SESSION_TTL_SECONDS,
                }
    raise RuntimeError("Could not allocate session id")
