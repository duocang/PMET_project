"""Process-tree termination shared between the API task-cancel endpoint
and the liveness watchdog.

Both call sites need to kill the bash workflow + every descendant: the
worker spawns shell pipelines that fork their own children, so killing
only the top PID leaves orphans running. Centralised here so the two
implementations cannot drift; importing this module pulls in nothing
from FastAPI or celery, keeping the watchdog container's footprint
small.
"""

from __future__ import annotations


def kill_process_tree(pid: int) -> list[int]:
    """SIGTERM (then SIGKILL after 5s) the process and every descendant.

    Returns the list of PIDs we attempted to terminate so the caller can
    audit if needed.
    """
    import psutil

    killed: list[int] = []
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return killed

    procs = [parent] + parent.children(recursive=True)
    for p in procs:
        try:
            p.terminate()
            killed.append(p.pid)
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(procs, timeout=5)
    for p in alive:
        try:
            p.kill()
        except psutil.NoSuchProcess:
            pass
    return killed
