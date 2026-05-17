"""Admin auth + settings endpoints.

Authentication model: shared bearer token from
``deploy/configure/admin_token.txt``. Login posts the token, server validates
against ``config.ADMIN_TOKEN`` and sets an httpOnly cookie. Subsequent admin
endpoints check the cookie via ``Depends(require_admin)``.

This is intentionally minimal — single-admin internal tool, not user RBAC.
"""

import hmac
import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pydantic import BaseModel

from ...config import config


router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_COOKIE = "pmet_admin"


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
async def login(payload: LoginPayload, response: Response):
    if not config.ADMIN_TOKEN:
        raise HTTPException(status_code=503, detail="Admin not configured")
    if not _token_matches(payload.token):
        raise HTTPException(status_code=401, detail="Invalid token")
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
async def logout(response: Response):
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
async def update_settings(payload: AdminSettings):
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
    return _settings_snapshot()
