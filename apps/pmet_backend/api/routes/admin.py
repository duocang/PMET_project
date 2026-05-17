"""Admin auth + settings endpoints.

Authentication model: shared bearer token from
``deploy/configure/admin_token.txt``. Login posts the token, server validates
against ``config.ADMIN_TOKEN`` and sets an httpOnly cookie. Subsequent admin
endpoints check the cookie via ``Depends(require_admin)``.

This is intentionally minimal — single-admin internal tool, not user RBAC.
"""

import hmac
import json
import secrets
import time
from collections import defaultdict
from pathlib import Path
from threading import Lock
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from ...config import config
from ...services import audit, cleanup, healthcheck


router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_COOKIE = "pmet_admin"

# Brute-force defence for /admin/login. We keep a process-local
# IP → (failures, window_start) map and gate the route on it. The
# canonical answer for multi-worker deploys is nginx's limit_req_zone
# (issue #18 already pushed general rate-limiting there) but the admin
# endpoint deserves a tighter, login-specific rule that lives next to
# the code it protects so a future operator can audit the policy
# without crawling the nginx config.
_LOGIN_FAILURE_WINDOW_SEC = 300   # 5 min sliding window
_LOGIN_MAX_FAILURES = 5
_LOGIN_LOCKOUT_SEC = 60
_login_failures: dict[str, list[float]] = defaultdict(list)
_login_lockouts: dict[str, float] = {}
_login_lock = Lock()


def _client_ip(request: Request) -> str:
    # Prefer X-Forwarded-For (we sit behind nginx). Fall back to
    # request.client.host for direct hits (dev / curl from host).
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _login_gate(ip: str) -> None:
    """Raise 429 if this IP is locked out or has too many recent failures."""
    now = time.monotonic()
    with _login_lock:
        # Active lockout still in effect?
        until = _login_lockouts.get(ip, 0.0)
        if until > now:
            retry_after = int(until - now) + 1
            raise HTTPException(
                status_code=429,
                detail="Too many login attempts; try again later",
                headers={"Retry-After": str(retry_after)},
            )


def _login_record_failure(ip: str) -> None:
    now = time.monotonic()
    with _login_lock:
        window = [t for t in _login_failures[ip] if now - t < _LOGIN_FAILURE_WINDOW_SEC]
        window.append(now)
        _login_failures[ip] = window
        if len(window) >= _LOGIN_MAX_FAILURES:
            _login_lockouts[ip] = now + _LOGIN_LOCKOUT_SEC
            # Clear the counter; the lockout itself is the next gate.
            _login_failures[ip] = []


def _login_record_success(ip: str) -> None:
    with _login_lock:
        _login_failures.pop(ip, None)
        _login_lockouts.pop(ip, None)


def _reset_login_state_for_tests() -> None:
    """Test-only — reset the in-memory counters between cases."""
    with _login_lock:
        _login_failures.clear()
        _login_lockouts.clear()


def _token_matches(candidate: Optional[str]) -> bool:
    """Constant-time comparison against the configured admin token.

    Plain ``==`` is timing-distinguishable on CPython's interpolated
    string compare and gives a small but real signal to a remote
    attacker. ``hmac.compare_digest`` walks both strings in fixed time
    even on a mismatch. Both inputs need a defined length first — an
    empty / None ``candidate`` is short-circuited above.
    """
    if not candidate or not config.ADMIN_TOKEN:
        return False
    return hmac.compare_digest(candidate, config.ADMIN_TOKEN)


class LoginPayload(BaseModel):
    token: str


class AdminSettings(BaseModel):
    notify_on_submit: Optional[bool] = None
    notify_user_on_start: Optional[bool] = None
    submissions_paused: Optional[bool] = None
    admin_notify_email: Optional[str] = None
    # 0 / negative is treated as "unset" — same convention used by the
    # config loader so the JSON file shape matches the API contract.
    minhash_threshold: Optional[int] = None
    result_retention_days: Optional[int] = None


def _settings_path() -> Path:
    return config.CONFIGURE_DIR / "admin_settings.json"


def require_admin(pmet_admin: Optional[str] = Cookie(default=None)) -> bool:
    """FastAPI dependency that 401s if the request lacks a valid admin cookie."""
    if not config.ADMIN_TOKEN:
        # Token not configured on the server — admin features disabled.
        raise HTTPException(status_code=503, detail="Admin not configured")
    if not _token_matches(pmet_admin):
        raise HTTPException(status_code=401, detail="Not authenticated")
    return True


@router.post("/login")
async def login(payload: LoginPayload, request: Request, response: Response):
    if not config.ADMIN_TOKEN:
        raise HTTPException(status_code=503, detail="Admin not configured")
    ip = _client_ip(request)
    _login_gate(ip)
    if not _token_matches(payload.token):
        _login_record_failure(ip)
        audit.emit(action="login_failed", ok=False, ip=ip)
        raise HTTPException(status_code=401, detail="Invalid token")
    _login_record_success(ip)
    audit.emit(action="login_ok", ok=True, ip=ip)
    # 30-day cookie. httpOnly + samesite=lax. Secure flag is omitted because
    # the dev stack runs over plain http on localhost; nginx in production
    # should add it via the proxy.
    response.set_cookie(
        key=ADMIN_COOKIE,
        value=config.ADMIN_TOKEN,
        max_age=60 * 60 * 24 * 30,
        httponly=True,
        samesite="lax",
    )
    return {"ok": True}


@router.post("/logout")
async def logout(request: Request, response: Response):
    audit.emit(action="logout", ok=True, ip=_client_ip(request))
    response.delete_cookie(ADMIN_COOKIE)
    return {"ok": True}


@router.get("/me")
async def me(pmet_admin: Optional[str] = Cookie(default=None)):
    """Used by the frontend to flip into admin mode. Returns 200 + is_admin
    rather than 401 so the frontend can render anonymously without spamming
    the console with errors.

    Also returns ``submissions_paused`` so the public /submit page can
    render the maintenance banner without exposing a dedicated public
    endpoint. The flag isn't sensitive — anyone hitting POST /tasks
    would learn about it anyway.
    """
    return {
        "is_admin": _token_matches(pmet_admin),
        "submissions_paused": config.SUBMISSIONS_PAUSED,
    }


def _settings_snapshot() -> dict:
    return {
        "notify_on_submit": config.NOTIFY_ON_SUBMIT,
        "notify_user_on_start": config.NOTIFY_USER_ON_START,
        "submissions_paused": config.SUBMISSIONS_PAUSED,
        "admin_notify_email": config.ADMIN_NOTIFY_EMAIL,
        "minhash_threshold": config.MINHASH_THRESHOLD,
        "result_retention_days": config.RESULT_RETENTION_DAYS,
    }


@router.get("/settings", dependencies=[Depends(require_admin)])
async def get_settings():
    return _settings_snapshot()


@router.put("/settings", dependencies=[Depends(require_admin)])
async def update_settings(payload: AdminSettings, request: Request):
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text()) or {}
            if not isinstance(existing, dict):
                existing = {}
        except json.JSONDecodeError:
            existing = {}
    # Preserve any sidecar fields (like _note) we don't manage.
    if payload.notify_on_submit is not None:
        existing["notify_on_submit"] = payload.notify_on_submit
    if payload.notify_user_on_start is not None:
        existing["notify_user_on_start"] = payload.notify_user_on_start
    if payload.submissions_paused is not None:
        existing["submissions_paused"] = payload.submissions_paused
    if payload.admin_notify_email is not None:
        # Empty string is a valid "clear the override" instruction; keep
        # the field present so the file shape stays predictable.
        existing["admin_notify_email"] = payload.admin_notify_email.strip()
    if payload.minhash_threshold is not None:
        # 0 / negative collapses to None (= "use default") to keep the
        # JSON file readable for the next operator.
        existing["minhash_threshold"] = (
            payload.minhash_threshold if payload.minhash_threshold > 0 else None
        )
    if payload.result_retention_days is not None:
        existing["result_retention_days"] = (
            payload.result_retention_days if payload.result_retention_days > 0 else None
        )
    path.write_text(json.dumps(existing, indent=2) + "\n")
    config.reload()
    audit.emit(
        action="settings_put",
        ok=True,
        ip=_client_ip(request),
        detail={k: v for k, v in payload.model_dump().items() if v is not None},
    )
    return _settings_snapshot()


@router.get("/audit", dependencies=[Depends(require_admin)])
async def get_audit(n: int = 200, category: Optional[str] = None):
    """Return the most-recent audit records (newest first). Capped at 1000
    server-side so an over-eager client can't make us read everything.
    """
    n = max(1, min(1000, n))
    return {"records": audit.read_tail(n=n, category=category)}


@router.get("/health/check", dependencies=[Depends(require_admin)])
async def health_check():
    """Run all admin self-test probes and return the combined report."""
    return healthcheck.run_all()


@router.get("/cleanup/preview", dependencies=[Depends(require_admin)])
async def cleanup_preview():
    """Cheap preview — how many tasks would the next sweep delete?"""
    days = config.RESULT_RETENTION_DAYS or 0
    return {
        "retention_days": days,
        "eligible": cleanup.count_eligible(days),
    }


@router.post("/cleanup/run", dependencies=[Depends(require_admin)])
async def cleanup_run(request: Request):
    """Sweep once. ``retention_days`` is read from current config; the
    operator changes it via the settings card."""
    days = config.RESULT_RETENTION_DAYS or 0
    report = cleanup.run(days)
    audit.emit(
        action="cleanup_run",
        ok=not report.get("skipped"),
        ip=_client_ip(request),
        detail=report,
    )
    return report


@router.post("/rotate-token", dependencies=[Depends(require_admin)])
async def rotate_token(request: Request, response: Response):
    """Generate a fresh 256-bit hex token, write it to
    ``admin_token.txt``, invalidate the current cookie, and return the
    new token *once* so the operator can copy it to a password manager.

    Existing sessions on other browsers / tabs are killed immediately —
    config.ADMIN_TOKEN updates in-process, so their cookie value no
    longer matches.
    """
    new_token = secrets.token_hex(32)
    path = config.CONFIGURE_DIR / "admin_token.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_token + "\n")
    config.reload()
    response.delete_cookie(ADMIN_COOKIE)
    audit.emit(
        action="rotate_token",
        ok=True,
        ip=_client_ip(request),
        detail={"length": len(new_token)},
    )
    return {"token": new_token}
