"""Admin self-test probes.

Each probe returns ``(status, detail)`` where status is one of
``"ok" | "warn" | "fail"``. Probes are deliberately non-destructive
(SMTP connects + EHLOs but doesn't send mail; redis pings; disk
queries usage; nothing writes to the FS).

Probes that hit external network resources have a small timeout so a
flaky upstream doesn't hang the /admin/health response.
"""

from __future__ import annotations

import os
import shutil
import socket
import tempfile
import time
from pathlib import Path

from ..config import config


def _smtp() -> tuple[str, dict]:
    """Connect → STARTTLS → AUTH → QUIT. No mail sent."""
    if not (config.EMAIL_USERNAME and config.EMAIL_PASSWORD and config.EMAIL_SERVER):
        return "warn", {"reason": "SMTP not configured (email_credential.txt)"}
    try:
        import smtplib
        port = int(config.EMAIL_PORT) if config.EMAIL_PORT else 587
        start = time.monotonic()
        with smtplib.SMTP(config.EMAIL_SERVER, port, timeout=5) as s:
            s.starttls()
            s.login(config.EMAIL_USERNAME, config.EMAIL_PASSWORD)
        return "ok", {
            "server": f"{config.EMAIL_SERVER}:{port}",
            "elapsed_ms": int((time.monotonic() - start) * 1000),
        }
    except Exception as e:
        return "fail", {"error": str(e)[:200]}


def _redis() -> tuple[str, dict]:
    """Plain TCP ping → blocking PING command on the redis broker."""
    broker = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/0")
    # Parse out host:port from redis://[:password@]host:port/db
    try:
        # quick parse — full URL grammar is overkill here
        without_scheme = broker.split("://", 1)[-1]
        without_auth = without_scheme.split("@", 1)[-1]
        hostport = without_auth.split("/", 1)[0]
        host, port_s = hostport.rsplit(":", 1) if ":" in hostport else (hostport, "6379")
        port = int(port_s)
    except Exception as e:
        return "fail", {"broker": broker, "error": f"parse: {e}"}

    try:
        start = time.monotonic()
        with socket.create_connection((host, port), timeout=2) as s:
            s.sendall(b"*1\r\n$4\r\nPING\r\n")
            reply = s.recv(64)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        if b"PONG" in reply:
            return "ok", {"host": host, "port": port, "elapsed_ms": elapsed_ms}
        return "warn", {"host": host, "port": port, "reply": reply.decode(errors="replace")}
    except Exception as e:
        return "fail", {"host": host, "port": port, "error": str(e)[:200]}


def _disk() -> tuple[str, dict]:
    """Disk usage on the RESULT_DIR partition."""
    try:
        usage = shutil.disk_usage(config.RESULT_DIR)
        free_gb = usage.free / (1024 ** 3)
        total_gb = usage.total / (1024 ** 3)
        pct_used = (usage.used / usage.total) * 100 if usage.total else 0
        status = "ok"
        if free_gb < 1.0:
            status = "fail"
        elif free_gb < 5.0:
            status = "warn"
        return status, {
            "path": str(config.RESULT_DIR),
            "free_gb": round(free_gb, 2),
            "total_gb": round(total_gb, 2),
            "pct_used": round(pct_used, 1),
        }
    except Exception as e:
        return "fail", {"error": str(e)[:200]}


def _tasks_dir_writable() -> tuple[str, dict]:
    """Try to create + delete a temp file inside TASKS_DIR."""
    try:
        config.TASKS_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=str(config.TASKS_DIR), prefix=".healthcheck_", delete=True
        ) as tmp:
            tmp.write(b"x")
            tmp.flush()
        return "ok", {"path": str(config.TASKS_DIR)}
    except Exception as e:
        return "fail", {"path": str(config.TASKS_DIR), "error": str(e)[:200]}


def _configure_dir() -> tuple[str, dict]:
    """Confirm operator-supplied files exist (or call out which ones are missing)."""
    files = {
        "admin_token.txt": (config.CONFIGURE_DIR / "admin_token.txt").exists(),
        "email_credential.txt": (config.CONFIGURE_DIR / "email_credential.txt").exists(),
        "public_base_url.txt": (config.CONFIGURE_DIR / "public_base_url.txt").exists(),
    }
    missing = [k for k, v in files.items() if not v]
    if "admin_token.txt" in missing:
        return "fail", {"missing": missing, "present": [k for k, v in files.items() if v]}
    if missing:
        return "warn", {"missing": missing, "present": [k for k, v in files.items() if v]}
    return "ok", {"present": list(files.keys())}


def run_all() -> dict:
    smtp_s, smtp_d = _smtp()
    redis_s, redis_d = _redis()
    disk_s, disk_d = _disk()
    tasks_s, tasks_d = _tasks_dir_writable()
    cfg_s, cfg_d = _configure_dir()
    return {
        "checks": [
            {"name": "smtp", "status": smtp_s, "detail": smtp_d},
            {"name": "redis", "status": redis_s, "detail": redis_d},
            {"name": "disk", "status": disk_s, "detail": disk_d},
            {"name": "tasks_dir", "status": tasks_s, "detail": tasks_d},
            {"name": "configure_dir", "status": cfg_s, "detail": cfg_d},
        ],
    }
