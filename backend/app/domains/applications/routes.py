from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db_session
from app.domains.accounts.dependencies import get_current_account
from app.domains.accounts.models import Account
from app.domains.application_accounts.service import ensure_target_ready
from app.domains.applications.models import ApplicationRun
from app.domains.applications.retry_policy import TerminalApplyError
from app.tasks.applications import enqueue_application_run
from app.domains.jobs.models import Job

router = APIRouter(prefix="/applications", tags=["applications"])

ACTION_NEEDED_STATUSES = {"action_needed", "platform_changed", "cooldown_required"}


class ActionNeededItemResponse(BaseModel):
    application_run_id: int
    job_id: int
    company_name: str
    title: str
    target_type: str | None
    run_status: str
    blocker_type: str
    last_step: str | None
    message: str | None
    artifact_paths: list[str]


class TriggerApplicationRunResponse(BaseModel):
    application_run_id: int
    status: str
    answer_entry_ids: list[int]
    created_question_task_ids: list[int]


def _extract_artifact_paths(payload: dict[str, Any]) -> list[str]:
    artifact_paths: list[str] = []
    for artifact in payload.get("artifacts", []):
        if isinstance(artifact, dict) and artifact.get("path"):
            artifact_paths.append(str(artifact["path"]))
        elif isinstance(artifact, str):
            artifact_paths.append(artifact)
    return artifact_paths


def serialize_action_needed_run(run: ApplicationRun) -> ActionNeededItemResponse:
    latest_event = max(run.events, key=lambda event: event.id, default=None)
    payload = latest_event.payload if latest_event else {}
    return ActionNeededItemResponse(
        application_run_id=run.id,
        job_id=run.job_id,
        company_name=run.job.company_name,
        title=run.job.title,
        target_type=run.apply_target.target_type if run.apply_target else None,
        run_status=run.status,
        blocker_type=str(payload.get("blocker_type", run.status)),
        last_step=payload.get("step"),
        message=payload.get("message"),
        artifact_paths=_extract_artifact_paths(payload),
    )


@router.get("/action-needed", response_model=list[ActionNeededItemResponse])
def list_action_needed_runs(
    current_account: Account = Depends(get_current_account),
    session: Session = Depends(get_db_session),
) -> list[ActionNeededItemResponse]:
    runs = session.scalars(
        select(ApplicationRun)
        .where(
            ApplicationRun.account_id == current_account.id,
            ApplicationRun.status.in_(ACTION_NEEDED_STATUSES),
        )
        .options(
            selectinload(ApplicationRun.job),
            selectinload(ApplicationRun.apply_target),
            selectinload(ApplicationRun.events),
        )
        .order_by(ApplicationRun.id.desc()),
    ).all()
    return [serialize_action_needed_run(run) for run in runs]


@router.post("/jobs/{job_id}/run", response_model=TriggerApplicationRunResponse)
def trigger_application_run(
    job_id: int,
    current_account: Account = Depends(get_current_account),
    session: Session = Depends(get_db_session),
) -> TriggerApplicationRunResponse:
    job = session.scalar(
        select(Job)
        .where(Job.id == job_id, Job.account_id == current_account.id)
        .options(selectinload(Job.apply_targets)),
    )
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if not job.apply_targets:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Job does not have an apply target",
        )

    preferred_target = next((target for target in job.apply_targets if target.is_preferred), None) or job.apply_targets[0]

    active_run = session.scalar(
        select(ApplicationRun).where(
            ApplicationRun.job_id == job_id,
            ApplicationRun.account_id == current_account.id,
            ApplicationRun.status.in_({"queued", "running"}),
        )
    )
    if active_run:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An application run is already active for this job (status: {active_run.status})",
        )

    try:
        ensure_target_ready(session, account_id=current_account.id, target=preferred_target)
        enqueue_application_run(job.id, current_account.email)
    except (TerminalApplyError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error

    return TriggerApplicationRunResponse(
        application_run_id=0,
        status="queued",
        answer_entry_ids=[],
        created_question_task_ids=[],
    )
