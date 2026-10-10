"""Background AI jobs: upload a document, keep working, open the result when it is ready."""

import base64
import binascii
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import sessionmaker

from kontor.api.ai import MAX_UPLOAD_CHARS, AnalyzeIn, analyze_statement
from kontor.api.deps import CurrentUser, DbSession
from kontor.api.documents import (
    AiDepotIn,
    analyze_contract,
    analyze_depot,
    analyze_financing,
)
from kontor.models import User
from kontor.services import jobs

router = APIRouter(prefix="/api/ai/jobs", tags=["ai"])

Kind = Literal["statement", "contract", "financing", "depot"]


class JobIn(BaseModel):
    kind: Kind
    filename: str = Field(max_length=200)
    content_base64: str = Field(max_length=MAX_UPLOAD_CHARS)
    mapping: dict[str, int] = Field(default_factory=dict)  # depot: ISIN -> instrument id
    person_id: int | None = None  # depot


class JobOut(BaseModel):
    id: str
    kind: Kind
    filename: str
    status: Literal["queued", "running", "waiting", "done", "failed"]
    error: str | None
    created_at: datetime
    finished_at: datetime | None


class JobDetail(JobOut):
    result: dict[str, Any] | None


def _when(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, UTC)


def _out(job: jobs.Job) -> JobOut:
    return JobOut(
        id=job.id,
        kind=job.kind,
        filename=job.filename,
        status=job.status,
        error=job.error,
        created_at=_when(job.created),
        finished_at=_when(job.finished) if job.finished else None,
    )


@router.get("", response_model=list[JobOut])
def list_jobs(user: CurrentUser) -> list[JobOut]:
    return [_out(j) for j in jobs.list_jobs(user.id)]


@router.post("", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
def start_job(body: JobIn, user: CurrentUser, db: DbSession) -> JobOut:
    try:
        base64.b64decode(body.content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Die Datei ist beschädigt."
        ) from exc
    if jobs.active_count(user.id) >= jobs.MAX_ACTIVE_PER_USER:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Es laufen schon mehrere Dokumente. Warte, bis eines fertig ist.",
        )
    user_id = user.id
    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    plain = AnalyzeIn(filename=body.filename, content_base64=body.content_base64)
    depot = AiDepotIn(
        filename=body.filename,
        content_base64=body.content_base64,
        mapping=body.mapping,
        person_id=body.person_id,
    )

    def work() -> dict[str, Any]:
        # the request is long over, so the job reads with a session and user of its own
        with factory() as session:
            owner = session.get(User, user_id)
            if owner is None:
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nicht angemeldet.")
            out: BaseModel
            if body.kind == "statement":
                out = analyze_statement(plain, owner, session)
            elif body.kind == "contract":
                out = analyze_contract(plain, owner, session)
            elif body.kind == "financing":
                out = analyze_financing(plain, owner)
            else:
                out = analyze_depot(depot, owner, session)
            session.rollback()  # reading only
            return out.model_dump(mode="json")

    return _out(jobs.submit(user_id, body.kind, body.filename, work))


@router.get("/{job_id}", response_model=JobDetail)
def get_job(job_id: str, user: CurrentUser) -> JobDetail:
    job = jobs.get(user.id, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Der Auftrag ist abgelaufen oder gelöscht.")
    return JobDetail(**_out(job).model_dump(), result=job.result)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def dismiss_job(job_id: str, user: CurrentUser) -> Response:
    jobs.remove(user.id, job_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
