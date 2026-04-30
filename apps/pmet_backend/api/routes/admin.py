"""Admin auth + settings endpoints.

Authentication model: shared bearer token from
``data/configure/admin_token.txt``. Login posts the token, server validates
against ``config.ADMIN_TOKEN`` and sets an httpOnly cookie. Subsequent admin
endpoints check the cookie via ``Depends(require_admin)``.

This is intentionally minimal — single-admin internal tool, not user RBAC.
"""

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pydantic import BaseModel

from ...config import config


router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_COOKIE = "pmet_admin"


class LoginPayload(BaseModel):
    token: str


class AdminSettings(BaseModel):
    notify_on_submit: Optional[bool] = None
    notify_user_on_start: Optional[bool] = None


def _settings_path() -> Path:
    return config.PROJECT_ROOT / "data" / "configure" / "admin_settings.json"


def require_admin(pmet_admin: Optional[str] = Cookie(default=None)) -> bool:
    """FastAPI dependency that 401s if the request lacks a valid admin cookie."""
    if not config.ADMIN_TOKEN:
        # Token not configured on the server — admin features disabled.
        raise HTTPException(status_code=503, detail="Admin not configured")
    if not pmet_admin or pmet_admin != config.ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return True


@router.post("/login")
async def login(payload: LoginPayload, response: Response):
    if not config.ADMIN_TOKEN:
        raise HTTPException(status_code=503, detail="Admin not configured")
    if payload.token != config.ADMIN_TOKEN:
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
    """
    is_admin = bool(
        config.ADMIN_TOKEN and pmet_admin and pmet_admin == config.ADMIN_TOKEN
    )
    return {"is_admin": is_admin}


@router.get("/settings", dependencies=[Depends(require_admin)])
async def get_settings():
    return {
        "notify_on_submit": config.NOTIFY_ON_SUBMIT,
        "notify_user_on_start": config.NOTIFY_USER_ON_START,
    }


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
    path.write_text(json.dumps(existing, indent=2) + "\n")
    config.reload()
    return {
        "notify_on_submit": config.NOTIFY_ON_SUBMIT,
        "notify_user_on_start": config.NOTIFY_USER_ON_START,
    }
