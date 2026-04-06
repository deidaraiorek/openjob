from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.accounts.dependencies import get_current_account
from app.domains.accounts.models import Account
from app.domains.sources.models import JobSource
from app.db.session import get_db_session
from app.tasks.discovery import sync_source

router = APIRouter(prefix="/sources", tags=["sources"])


class SourceCreateRequest(BaseModel):
    source_key: str
    source_type: str
    name: str
    base_url: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)
    active: bool = True


class SourceUpdateRequest(BaseModel):
    source_key: str
    source_type: str
    name: str
    base_url: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)
    active: bool = True


class SourceResponse(BaseModel):
    id: int
    source_key: str
    source_type: str
    name: str
    base_url: str | None
    settings: dict[str, Any]
    active: bool


class SourceSyncResponse(BaseModel):
    source_id: int
    source_key: str
    source_type: str
    processed: int
    created: int
    updated: int


def serialize_source(source: JobSource) -> SourceResponse:
    return SourceResponse(
        id=source.id,
        source_key=source.source_key,
        source_type=source.source_type,
        name=source.name,
        base_url=source.base_url,
        settings=source.settings_json,
        active=source.active,
    )


@router.get("", response_model=list[SourceResponse])
def list_sources(
    current_account: Account = Depends(get_current_account),
    session: Session = Depends(get_db_session),
) -> list[SourceResponse]:
    sources = session.scalars(
        select(JobSource)
        .where(JobSource.account_id == current_account.id)
        .order_by(JobSource.name.asc())
    ).all()
    return [serialize_source(source) for source in sources]


@router.post("", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
def create_source(
    payload: SourceCreateRequest,
    current_account: Account = Depends(get_current_account),
    session: Session = Depends(get_db_session),
) -> SourceResponse:
    existing = session.scalar(
        select(JobSource).where(
            JobSource.account_id == current_account.id,
            JobSource.source_key == payload.source_key,
        ),
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Source key already exists for this account",
        )

    source = JobSource(
        account_id=current_account.id,
        source_key=payload.source_key,
        source_type=payload.source_type,
        name=payload.name,
        base_url=payload.base_url,
        settings_json=payload.settings,
        active=payload.active,
    )
    session.add(source)
    session.commit()
    session.refresh(source)
    return serialize_source(source)


@router.put("/{source_id}", response_model=SourceResponse)
def update_source(
    source_id: int,
    payload: SourceUpdateRequest,
    current_account: Account = Depends(get_current_account),
    session: Session = Depends(get_db_session),
) -> SourceResponse:
    source = session.scalar(
        select(JobSource).where(
            JobSource.id == source_id,
            JobSource.account_id == current_account.id,
        ),
    )
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")

    conflicting = session.scalar(
        select(JobSource).where(
            JobSource.account_id == current_account.id,
            JobSource.source_key == payload.source_key,
            JobSource.id != source_id,
        ),
    )
    if conflicting:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Source key already exists for this account",
        )

    source.source_key = payload.source_key
    source.source_type = payload.source_type
    source.name = payload.name
    source.base_url = payload.base_url
    source.settings_json = payload.settings
    source.active = payload.active

    session.commit()
    session.refresh(source)
    return serialize_source(source)


@router.post("/{source_id}/sync", response_model=SourceSyncResponse)
def trigger_source_sync(
    source_id: int,
    current_account: Account = Depends(get_current_account),
    session: Session = Depends(get_db_session),
) -> SourceSyncResponse:
    source = session.scalar(
        select(JobSource).where(
            JobSource.id == source_id,
            JobSource.account_id == current_account.id,
        ),
    )
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")

    try:
        summary = sync_source(session, source.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return SourceSyncResponse(
        source_id=source.id,
        source_key=source.source_key,
        source_type=source.source_type,
        processed=summary["processed"],
        created=summary["created"],
        updated=summary["updated"],
    )
