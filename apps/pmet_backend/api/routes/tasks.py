from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from datetime import datetime
import json

from ..models.task import TaskCreate, TaskResponse, TaskStatus, TaskMode, TaskListResponse
from ...config import config
from ...services.storage import StorageService

router = APIRouter(prefix="/tasks", tags=["tasks"])
storage = StorageService()


@router.post("", response_model=TaskResponse)
async def create_task(task: TaskCreate):
    """Create a new PMET task"""
    task_id = storage.generate_task_id(task.email, override=task.task_id)
    task_dir = storage.create_task_directory(task_id)

    # Save task metadata. Overwrite the (optional) inbound task_id with the
    # validated server-side value so downstream consumers always see the
    # canonical id.
    task_meta = task.model_dump()
    task_meta["task_id"] = task_id
    task_meta["status"] = TaskStatus.PENDING.value
    task_meta["created_at"] = datetime.utcnow().isoformat()

    meta_file = config.TASKS_DIR / f"{task_id}.json"
    meta_file.parent.mkdir(parents=True, exist_ok=True)
    meta_file.write_text(json.dumps(task_meta, indent=2))

    # Build result link
    result_link = f"{config.NGINX_LINK}{task_id}.zip" if config.NGINX_LINK else None

    # Submit to Celery (import here to avoid circular dependency)
    from ...worker.tasks.pmet import run_pmet_task
    run_pmet_task.delay(task_meta, str(task_dir))

    return TaskResponse(
        task_id=task_id,
        status=TaskStatus.PENDING,
        mode=task.mode,
        email=task.email,
        result_link=result_link,
        created_at=datetime.utcnow(),
    )


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str):
    """Get task status and details"""
    task_file = config.TASKS_DIR / f"{task_id}.json"
    if not task_file.exists():
        raise HTTPException(status_code=404, detail="Task not found")

    task_data = json.loads(task_file.read_text())

    # Check if result exists
    result_zip = config.RESULT_DIR / f"{task_id}.zip"
    if result_zip.exists():
        task_data["status"] = TaskStatus.COMPLETED.value
        task_data["completed_at"] = datetime.fromtimestamp(
            result_zip.stat().st_mtime
        ).isoformat()

    # Synthesize the public link if the worker hasn't persisted one yet
    # (older JSONs, or in-flight tasks) but the zip + nginx base exist.
    result_link = task_data.get("result_link")
    if not result_link and config.NGINX_LINK and result_zip.exists():
        result_link = f"{config.NGINX_LINK.rstrip('/')}/{task_id}.zip"

    return TaskResponse(
        task_id=task_data["task_id"],
        status=TaskStatus(task_data.get("status", "pending")),
        mode=TaskMode(task_data["mode"]),
        email=task_data["email"],
        result_link=result_link,
        created_at=datetime.fromisoformat(task_data["created_at"]),
        started_at=datetime.fromisoformat(task_data["started_at"]) if task_data.get("started_at") else None,
        completed_at=datetime.fromisoformat(task_data["completed_at"]) if task_data.get("completed_at") else None,
        error_message=task_data.get("error_message"),
    )


@router.get("/{task_id}/result")
async def download_result(task_id: str):
    """Download task result as zip file"""
    result_zip = config.RESULT_DIR / f"{task_id}.zip"
    if not result_zip.exists():
        raise HTTPException(status_code=404, detail="Result not found")
    return FileResponse(result_zip, media_type="application/zip", filename=f"{task_id}.zip")


@router.get("", response_model=TaskListResponse)
async def list_tasks(email: str = None, task_id: str = None, limit: int = 50, offset: int = 0):
    """List tasks. Filter by exact email match, by task_id substring, or both."""
    tasks = []
    for task_file in sorted(config.TASKS_DIR.glob("*.json"), reverse=True)[offset:offset+limit]:
        task_data = json.loads(task_file.read_text())
        if email and task_data.get("email") != email:
            continue
        if task_id and task_id not in task_data.get("task_id", ""):
            continue

        status = TaskStatus(task_data.get("status", "pending"))
        result_zip = config.RESULT_DIR / f"{task_data['task_id']}.zip"
        if result_zip.exists():
            status = TaskStatus.COMPLETED

        tasks.append(TaskResponse(
            task_id=task_data["task_id"],
            status=status,
            mode=TaskMode(task_data["mode"]),
            email=task_data["email"],
            result_link=task_data.get("result_link"),
            created_at=datetime.fromisoformat(task_data["created_at"]),
            started_at=datetime.fromisoformat(task_data["started_at"]) if task_data.get("started_at") else None,
            completed_at=datetime.fromisoformat(task_data["completed_at"]) if task_data.get("completed_at") else None,
            error_message=task_data.get("error_message"),
        ))

    return TaskListResponse(tasks=tasks, total=len(tasks))
