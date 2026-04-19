from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db_session
from app.domains.accounts.dependencies import get_admin_account, get_current_account
from app.domains.accounts.models import Account
from app.domains.applications.models import ApplicationEvent, ApplicationRun
from app.domains.logs.models import SystemEvent

router = APIRouter(tags=["logs"])


class SystemEventResponse(BaseModel):
    id: int
    account_id: int | None
    event_type: str
    source: str
    payload: dict[str, Any]
    created_at: str


class QuestionAnswerEntry(BaseModel):
    question_fingerprint: str
    prompt_text: str
    field_type: str
    required: bool
    option_labels: list[str]
    placeholder_text: str | None
    match_source: str
    answer_entry_id: int | None
    answer_label: str | None
    answer_value: Any


class ApplicationEventResponse(BaseModel):
    id: int
    event_type: str
    payload: dict[str, Any]
    created_at: str


class ApplicationRunLogResponse(BaseModel):
    application_run_id: int
    job_id: int
    status: str
    apply_target_type: str | None
    started_at: str
    completed_at: str | None
    events: list[ApplicationEventResponse]
    question_answer_map: list[QuestionAnswerEntry]


@router.get("/logs/system", response_model=list[SystemEventResponse])
def list_system_events(
    source: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    current_account: Account = Depends(get_admin_account),
    session: Session = Depends(get_db_session),
) -> list[SystemEventResponse]:
    stmt = select(SystemEvent).order_by(SystemEvent.created_at.desc()).limit(limit).offset(offset)
    if source:
        stmt = stmt.where(SystemEvent.source == source)
    if event_type:
        stmt = stmt.where(SystemEvent.event_type == event_type)

    events = session.scalars(stmt).all()
    return [
        SystemEventResponse(
            id=event.id,
            account_id=event.account_id,
            event_type=event.event_type,
            source=event.source,
            payload=event.payload,
            created_at=event.created_at.isoformat(),
        )
        for event in events
    ]


@router.get("/applications/runs/{run_id}/log", response_model=ApplicationRunLogResponse)
def get_application_run_log(
    run_id: int,
    current_account: Account = Depends(get_current_account),
    session: Session = Depends(get_db_session),
) -> ApplicationRunLogResponse:
    run = session.scalar(
        select(ApplicationRun)
        .where(
            ApplicationRun.id == run_id,
            ApplicationRun.account_id == current_account.id,
        )
        .options(
            selectinload(ApplicationRun.events),
            selectinload(ApplicationRun.apply_target),
        )
    )
    if not run:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Application run not found")

    submitted_event = next(
        (e for e in sorted(run.events, key=lambda e: e.id, reverse=True) if e.payload.get("question_answer_map")),
        None,
    )
    raw_map = submitted_event.payload.get("question_answer_map", []) if submitted_event else []
    question_answer_map = [
        QuestionAnswerEntry(
            question_fingerprint=item.get("question_fingerprint", ""),
            prompt_text=item.get("prompt_text", ""),
            field_type=item.get("field_type", ""),
            required=item.get("required", False),
            option_labels=item.get("option_labels", []),
            placeholder_text=item.get("placeholder_text"),
            match_source=item.get("match_source", "unresolved"),
            answer_entry_id=item.get("answer_entry_id"),
            answer_label=item.get("answer_label"),
            answer_value=item.get("answer_value"),
        )
        for item in raw_map
    ]

    return ApplicationRunLogResponse(
        application_run_id=run.id,
        job_id=run.job_id,
        status=run.status,
        apply_target_type=run.apply_target.target_type if run.apply_target else None,
        started_at=run.started_at.isoformat(),
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
        events=[
            ApplicationEventResponse(
                id=event.id,
                event_type=event.event_type,
                payload={k: v for k, v in event.payload.items() if k != "question_answer_map"},
                created_at=event.created_at.isoformat(),
            )
            for event in sorted(run.events, key=lambda e: e.id)
        ],
        question_answer_map=question_answer_map,
    )
