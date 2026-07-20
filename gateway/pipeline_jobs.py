import asyncio
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set

MAX_EVENTS_PER_JOB = 500
JOB_TTL_SECONDS = 900  # 15 minutes

@dataclass
class PipelineJob:
    job_id: str
    status: str  # "running" | "complete" | "degraded" | "failed" | "cancelled"
    cancel_event: threading.Event = field(default_factory=threading.Event)
    worker_thread: Optional[threading.Thread] = None
    result: Optional[Dict[str, Any]] = None
    event_journal: deque = field(default_factory=lambda: deque(maxlen=MAX_EVENTS_PER_JOB))
    subscribers: Set = field(default_factory=set)
    created_at: float = field(default_factory=time.time)
    terminal_at: Optional[float] = None

class PipelineJobManager:
    def __init__(self):
        self._lock = threading.RLock()
        self._current_job: Optional[PipelineJob] = None

    def create_job(self) -> PipelineJob:
        """Create a new job. Raises RuntimeError if one is already running."""
        with self._lock:
            if self._current_job and self._current_job.status == "running":
                raise RuntimeError("A job is already running")
            job = PipelineJob(
                job_id=f"job_{uuid.uuid4().hex}",
                status="running",
                cancel_event=threading.Event()
            )
            self._current_job = job
            return job

    def get_job(self, job_id: str) -> Optional[PipelineJob]:
        with self._lock:
            if self._current_job and self._current_job.job_id == job_id:
                return self._current_job
            return None

    def record_event(self, job: PipelineJob, event: dict) -> None:
        with self._lock:
            job.event_journal.append(event)

    def finalize_job(self, job: PipelineJob, status: str, result: dict) -> None:
        with self._lock:
            job.status = status
            job.result = result
            job.terminal_at = time.time()

job_manager = PipelineJobManager()
