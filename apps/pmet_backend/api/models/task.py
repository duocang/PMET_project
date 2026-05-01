from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class TaskMode(str, Enum):
    PROMOTERS_PRE = "promoters_pre"
    PROMOTERS = "promoters"
    INTERVALS = "intervals"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskCreate(BaseModel):
    email: EmailStr
    mode: TaskMode
    # Frontend-generated UUID used as both the upload-session id (uploaded
    # files land under results/app/<task_id>/upload/) and the task id. Optional
    # for legacy / curl callers — the server falls back to an email-stamped
    # id if not provided.
    task_id: Optional[str] = None

    # Common parameters
    ic_threshold: int = Field(default=24, ge=2, le=32)
    max_match: int = Field(default=5, ge=2, le=20)
    promoter_num: int = Field(default=5000)
    fimo_threshold: float = Field(default=0.05)

    # promoters mode specific
    promoter_length: Optional[int] = Field(default=1000)
    utr5: Optional[str] = Field(default="No")
    promoters_overlap: Optional[str] = Field(default="NoOverlap")

    # File paths (relative to result dir)
    genes_file: str
    fasta_file: Optional[str] = None
    gff3_file: Optional[str] = None
    meme_file: Optional[str] = None
    premade_index: Optional[str] = None


class TaskResponse(BaseModel):
    task_id: str
    status: TaskStatus
    mode: TaskMode
    email: str
    result_link: Optional[str] = None
    # Set when status==failed but the pairing stage finished and
    # motif_output.txt is on disk. Lets the user download partial
    # scientific output even after the late-stage (heatmap / zip)
    # crash that flipped the task to failed. Points at
    # /api/tasks/<id>/partial-result.
    partial_result_link: Optional[str] = None
    # Size of motif_output.txt in bytes when partial_result_link is set, so
    # the UI can label the download with how big the user is about to pull.
    # On big libraries × many clusters this can hit the GB range.
    partial_result_size_bytes: Optional[int] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    # Parameters the task was submitted with — surfaced on the detail page
    # so a user inspecting an old run can see exactly what was asked for.
    ic_threshold: Optional[int] = None
    max_match: Optional[int] = None
    promoter_num: Optional[int] = None
    fimo_threshold: Optional[float] = None
    promoter_length: Optional[int] = None
    utr5: Optional[str] = None
    promoters_overlap: Optional[str] = None

    # Input file paths (relative to repo root). The detail page only
    # displays the basename; full path is preserved for debugging.
    genes_file: Optional[str] = None
    fasta_file: Optional[str] = None
    gff3_file: Optional[str] = None
    meme_file: Optional[str] = None
    premade_index: Optional[str] = None
    indexing_species: Optional[str] = None
    indexing_motif_db: Optional[str] = None
    runtime_estimate: Optional[dict] = None

    # Worker thread count read from current config (data/configure/
    # cpu_configuration.txt). Not historically frozen — reflects what
    # the worker would use *now* if the same task were rerun.
    ncpu: Optional[int] = None

    # Filesystem-derived per-stage view (services/stage_status.py). The
    # binary `status` field above is the worker's authority; `stages`
    # adds the "WHICH stage produced output" detail that lets the UI
    # render a timeline + warnings panel without changing the persisted
    # status. Each stage entry: {name, state, note?}.
    stages: Optional[list[dict]] = None
    # Human-readable warnings derived from skipped stages with notes
    # (e.g. "heatmap: rendering failed; motif_output.txt is complete").
    warnings: Optional[list[str]] = None
    # Display-only label that may be `completed_with_warnings` when a
    # successful task had a non-fatal skip. UI uses this for badge
    # text/colour; never overwrites the persisted `status`.
    effective_status: Optional[str] = None

    class Config:
        from_attributes = True


class TaskListResponse(BaseModel):
    tasks: list[TaskResponse]
    total: int
