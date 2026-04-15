from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.accounts.dependencies import get_current_account
from app.domains.accounts.models import Account
from app.domains.sources.models import JobSource
from app.domains.sources.sync_control import (
    acquire_source_sync_lease,
    apply_source_schedule_defaults,
    mark_source_synced,
    normalize_sync_interval_hours,
    release_source_sync_lease,
)
from app.domains.sources.url_normalization import normalize_github_curated_url
from app.db.session import get_db_session
from app.tasks.discovery import sync_source
from app.tasks.job_relevance import drain_relevance_tasks_for_account

router = APIRouter(prefix="/sources", tags=["sources"])


class SourceCreateRequest(BaseModel):
    source_key: str
    source_type: str
    name: str
    base_url: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)
    active: bool = True
    auto_sync_enabled: bool = True
    sync_interval_hours: int | None = None


class SourceUpdateRequest(BaseModel):
    source_key: str
    source_type: str
    name: str
    base_url: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)
    active: bool = True
    auto_sync_enabled: bool = True
    sync_interval_hours: int | None = None


class SourceResponse(BaseModel):
    id: int
    source_key: str
    source_type: str
    name: str
    base_url: str | None
    settings: dict[str, Any]
    active: bool
    auto_sync_enabled: bool
    sync_interval_hours: int
    last_synced_at: datetime | None
    last_sync_summary: dict[str, int]
    next_sync_at: datetime | None


class SourceSyncResponse(BaseModel):
    source_id: int
    source_key: str
    source_type: str
    processed: int
    created: int
    updated: int
    pending_title_screening: int
    pending_full_relevance: int
    api_compatible_targets: int
    browser_compatible_targets: int
    manual_only_targets: int
    resolution_failed_targets: int
    last_synced_at: datetime | None
    next_sync_at: datetime | None


def normalize_source_payload(
    *,
    source_type: str,
    base_url: str | None,
    settings: dict[str, Any],
) -> tuple[str | None, dict[str, Any]]:
    normalized_base_url = base_url
    normalized_settings = dict(settings)
    if source_type == "github_curated":
        normalized_base_url = normalize_github_curated_url(base_url)
        normalized_settings.pop("raw_url", None)
    return normalized_base_url, normalized_settings


def _as_utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def serialize_source(source: JobSource) -> SourceResponse:
    return SourceResponse(
        id=source.id,
        source_key=source.source_key,
        source_type=source.source_type,
        name=source.name,
        base_url=source.base_url,
        settings=source.settings_json,
        active=source.active,
        auto_sync_enabled=source.auto_sync_enabled,
        sync_interval_hours=source.sync_interval_hours,
        last_synced_at=_as_utc_datetime(source.last_synced_at),
        last_sync_summary=source.last_sync_summary_json or {},
        next_sync_at=_as_utc_datetime(source.next_sync_at),
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

    try:
        normalized_base_url, normalized_settings = normalize_source_payload(
            source_type=payload.source_type,
            base_url=payload.base_url,
            settings=payload.settings,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    source = JobSource(
        account_id=current_account.id,
        source_key=payload.source_key,
        source_type=payload.source_type,
        name=payload.name,
        base_url=normalized_base_url,
        settings_json=normalized_settings,
        active=payload.active,
        auto_sync_enabled=payload.auto_sync_enabled,
        sync_interval_hours=normalize_sync_interval_hours(payload.sync_interval_hours),
    )
    apply_source_schedule_defaults(source)
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

    try:
        normalized_base_url, normalized_settings = normalize_source_payload(
            source_type=payload.source_type,
            base_url=payload.base_url,
            settings=payload.settings,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    source.source_key = payload.source_key
    source.source_type = payload.source_type
    source.name = payload.name
    source.base_url = normalized_base_url
    source.settings_json = normalized_settings
    source.active = payload.active
    source.auto_sync_enabled = payload.auto_sync_enabled
    source.sync_interval_hours = normalize_sync_interval_hours(payload.sync_interval_hours)
    apply_source_schedule_defaults(source)

    session.commit()
    session.refresh(source)
    return serialize_source(source)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(
    source_id: int,
    current_account: Account = Depends(get_current_account),
    session: Session = Depends(get_db_session),
) -> None:
    source = session.scalar(
        select(JobSource).where(
            JobSource.id == source_id,
            JobSource.account_id == current_account.id,
        ),
    )
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")

    session.delete(source)
    session.commit()


@router.post("/{source_id}/sync", response_model=SourceSyncResponse)
def trigger_source_sync(
    source_id: int,
    background_tasks: BackgroundTasks,
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
    if not source.active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive sources must be reactivated before syncing.",
        )

    if not acquire_source_sync_lease(session, source_id=source.id):
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This source is already syncing. Wait for it to finish before starting another run.",
        )
    session.commit()

    try:
        summary = sync_source(session, source.id)
        source.last_sync_summary_json = summary
        mark_source_synced(source)
        session.commit()
    except ValueError as exc:
        release_source_sync_lease(session, source_id=source.id)
        session.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception:
        release_source_sync_lease(session, source_id=source.id)
        session.commit()
        raise

    if summary["pending_title_screening"] or summary["pending_full_relevance"]:
        background_tasks.add_task(drain_relevance_tasks_for_account, current_account.id)

    return SourceSyncResponse(
        source_id=source.id,
        source_key=source.source_key,
        source_type=source.source_type,
        processed=summary["processed"],
        created=summary["created"],
        updated=summary["updated"],
        pending_title_screening=summary["pending_title_screening"],
        pending_full_relevance=summary["pending_full_relevance"],
        api_compatible_targets=summary["api_compatible_targets"],
        browser_compatible_targets=summary["browser_compatible_targets"],
        manual_only_targets=summary["manual_only_targets"],
        resolution_failed_targets=summary["resolution_failed_targets"],
        last_synced_at=_as_utc_datetime(source.last_synced_at),
        next_sync_at=_as_utc_datetime(source.next_sync_at),
    )
