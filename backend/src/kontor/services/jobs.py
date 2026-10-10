"""Background jobs for AI document reading.

Reading a document with a local model can take minutes, and the machine may first have to wake up
and load the model. A job runs on one worker thread (one request at a time, the GPU is shared) and
keeps its result in memory until the user opens or dismisses it. Nothing is written to the
database and the uploaded file is dropped as soon as the job ends. Jobs do not survive a restart
of the API, which is acceptable for something that can be uploaded again.
"""

import logging
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi import HTTPException

from kontor.core.config import get_settings

log = logging.getLogger(__name__)

Status = Literal["queued", "running", "waiting", "done", "failed"]
KEEP_SECONDS = 24 * 3600
MAX_ACTIVE_PER_USER = 5


@dataclass
class Job:
    id: str
    user_id: int
    kind: str
    filename: str
    status: Status = "queued"
    result: dict[str, Any] | None = None
    error: str | None = None
    created: float = field(default_factory=time.time)
    finished: float | None = None
    cancelled: bool = False


_jobs: dict[str, Job] = {}
_lock = threading.Lock()
_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="kontor-ai")


def _purge() -> None:
    cutoff = time.time() - KEEP_SECONDS
    for job_id in [j.id for j in _jobs.values() if j.created < cutoff]:
        _jobs.pop(job_id, None)


def active_count(user_id: int) -> int:
    with _lock:
        return sum(1 for j in _jobs.values() if j.user_id == user_id and j.finished is None)


def list_jobs(user_id: int) -> list[Job]:
    with _lock:
        _purge()
        return sorted((j for j in _jobs.values() if j.user_id == user_id), key=lambda j: j.created)


def get(user_id: int, job_id: str) -> Job | None:
    with _lock:
        job = _jobs.get(job_id)
        return job if job is not None and job.user_id == user_id else None


def remove(user_id: int, job_id: str) -> bool:
    with _lock:
        job = _jobs.get(job_id)
        if job is None or job.user_id != user_id:
            return False
        job.cancelled = True
        del _jobs[job_id]
        return True


def _finish(job: Job, *, result: dict[str, Any] | None = None, error: str | None = None) -> None:
    with _lock:
        job.result = result
        job.error = error
        job.status = "done" if error is None else "failed"
        job.finished = time.time()


def _run(job: Job, work: Callable[[], dict[str, Any]]) -> None:
    settings = get_settings()
    deadline = time.time() + settings.ai_wait_minutes * 60
    while not job.cancelled:
        job.status = "running"
        try:
            _finish(job, result=work())
            return
        except HTTPException as exc:
            # 503: the AI server is off or still loading its model; keep trying for a while
            if exc.status_code == 503 and time.time() < deadline:
                job.status = "waiting"
                end = time.time() + settings.ai_retry_seconds
                while time.time() < end and not job.cancelled:
                    time.sleep(min(0.2, settings.ai_retry_seconds))
                continue
            _finish(job, error=str(exc.detail))
            return
        except Exception:
            log.exception("AI job %s failed", job.id)
            _finish(job, error="Beim Lesen des Dokuments ist ein Fehler aufgetreten.")
            return


def submit(user_id: int, kind: str, filename: str, work: Callable[[], dict[str, Any]]) -> Job:
    job = Job(id=uuid.uuid4().hex, user_id=user_id, kind=kind, filename=filename[:200])
    with _lock:
        _purge()
        _jobs[job.id] = job
    _pool.submit(_run, job, work)
    return job
