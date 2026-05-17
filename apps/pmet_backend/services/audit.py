"""Append-only admin / mail audit log.

One JSONL file at ``CONFIGURE_DIR/admin_audit.jsonl`` so destructive
admin actions (login attempts, settings PUT, task termination, token
rotation, mail send attempts) leave a trail. Used by both the admin
audit endpoint and the mail dispatcher.

Design notes:

- Append-only JSONL — easy for humans to ``tail``, easy for the API to
  ``readlines()`` and reverse for "newest first" rendering.
- No fsync per write. A crash loses at most a few lines, which is
  acceptable for a single-admin internal tool. The alternative
  (sqlite, structured logger) doesn't earn its weight here.
- Reading is capped at the last N lines so a runaway log doesn't OOM
  the api process.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from threading import Lock
from typing import Any, Optional

from ..config import config


_audit_lock = Lock()
# 5 MB cap before rotation. Generous — at ~200 B/line that's ~25 k
# events; an admin doing 10 actions/day takes years to fill it.
_MAX_BYTES = 5 * 1024 * 1024


def _path() -> Path:
    return config.CONFIGURE_DIR / "admin_audit.jsonl"


def _rotate_if_needed(p: Path) -> None:
    try:
        if p.exists() and p.stat().st_size > _MAX_BYTES:
            backup = p.with_suffix(".jsonl.1")
            try:
                if backup.exists():
                    backup.unlink()
            except OSError:
                pass
            try:
                p.rename(backup)
            except OSError:
                pass
    except OSError:
        # Stat failure shouldn't kill an audit write — just append.
        pass


def emit(
    *,
    action: str,
    ok: bool = True,
    ip: Optional[str] = None,
    target: Optional[str] = None,
    detail: Optional[Any] = None,
    category: str = "admin",
) -> None:
    """Append one audit record. Never raises — audit failure must not
    take down the action being audited.

    Fields:
      ts        — ISO 8601 UTC
      category  — "admin" | "mail"
      action    — short verb ("login_ok", "settings_put", "terminate", "mail_send", ...)
      ok        — outcome boolean
      ip        — client IP for human actions; None for system actions
      target    — what was acted on (task_id, settings key, etc.)
      detail    — free-form dict / string with extra context
    """
    rec = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "category": category,
        "action": action,
        "ok": ok,
        "ip": ip,
        "target": target,
        "detail": detail,
    }
    line = json.dumps(rec, ensure_ascii=False, default=str) + "\n"
    p = _path()
    try:
        with _audit_lock:
            p.parent.mkdir(parents=True, exist_ok=True)
            _rotate_if_needed(p)
            with p.open("a", encoding="utf-8") as f:
                f.write(line)
    except OSError:
        # Best-effort. Operators can still grep the docker logs.
        pass


def read_tail(n: int = 200, category: Optional[str] = None) -> list[dict]:
    """Return the last ``n`` audit records, newest first.

    ``category`` filters in-memory (cheap — we only hold N lines anyway).
    """
    p = _path()
    if not p.exists():
        return []
    try:
        # Reading the whole file is OK while we cap at 5 MB. For larger
        # files we'd want a reverse-streaming reader.
        with p.open("r", encoding="utf-8") as f:
            raw = f.readlines()
    except OSError:
        return []

    out: list[dict] = []
    for line in reversed(raw):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if category and rec.get("category") != category:
            continue
        out.append(rec)
        if len(out) >= n:
            break
    return out
