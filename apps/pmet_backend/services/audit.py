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

import ipaddress
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Optional

from ..config import config


_audit_lock = Lock()
# 5 MB cap before rotation. Generous — at ~200 B/line that's ~25 k
# events; an admin doing 10 actions/day takes years to fill it.
_MAX_BYTES = 5 * 1024 * 1024

# Time-based retention. GDPR's "storage limitation" principle (Art.
# 5(1)(e)) — we don't keep audit records beyond what's needed for the
# legitimate-interest basis they're recorded under. Records older than
# this are filtered out at read time. The size-based rotation above
# eventually drops them from disk too; the time filter just makes sure
# they're invisible immediately.
_RETENTION_DAYS = 30


def _anonymize_ip(ip: Optional[str]) -> Optional[str]:
    """Truncate user IPs for GDPR data minimisation (Art. 5(1)(c)).

    - IPv4: zero the last octet (e.g. ``192.168.65.7`` → ``192.168.65.0``)
    - IPv6: zero everything past the first 64 bits (the host id)
    - Anything we can't parse (``"unknown"``, malformed strings, None)
      is passed through unchanged — the audit row still records
      *something* useful, we just can't anonymise what we can't parse.

    The /24 + /64 truncation is the European data-protection authority
    consensus for "enough geo/ASN detail to defend against attacks,
    not enough to identify an individual".
    """
    if not ip:
        return ip
    try:
        parsed = ipaddress.ip_address(ip)
    except (ValueError, TypeError):
        return ip
    if isinstance(parsed, ipaddress.IPv4Address):
        return str(ipaddress.ip_network(f"{ip}/24", strict=False).network_address)
    # IPv6 — keep the first 64 bits, zero the rest.
    return str(ipaddress.ip_network(f"{ip}/64", strict=False).network_address)


def _within_retention(ts_iso: str, now: datetime) -> bool:
    """True if ``ts_iso`` is at most ``_RETENTION_DAYS`` old vs ``now``.

    Records with unparseable / missing ts are kept (visible) — they're
    presumed fresh corrupt-line garbage, and dropping them silently
    would hide bugs in the writer.
    """
    if not ts_iso:
        return True
    try:
        # We write "YYYY-MM-DDTHH:MM:SSZ" so fromisoformat handles it
        # cleanly after stripping the trailing 'Z'.
        ts = datetime.fromisoformat(ts_iso.rstrip("Z")).replace(tzinfo=timezone.utc)
    except ValueError:
        return True
    return (now - ts) <= timedelta(days=_RETENTION_DAYS)


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
        # IP is anonymised at the data-minimisation layer (Art. 5(1)(c)
        # GDPR) before it ever touches disk. /24 for IPv4, /64 for IPv6.
        "ip": _anonymize_ip(ip),
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
    now = datetime.now(tz=timezone.utc)
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
        # Time-based retention filter (GDPR Art. 5(1)(e)). Older records
        # are still on disk until the next 5 MB rotation drops them, but
        # they're invisible to every reader from this point.
        if not _within_retention(rec.get("ts", ""), now):
            continue
        out.append(rec)
        if len(out) >= n:
            break
    return out
