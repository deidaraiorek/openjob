from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domains.sources.models import JobSource


def utcnow() -> datetime:
    return datetime.now(UTC)


def default_sync_interval_hours() -> int:
    settings = get_settings()
    return max(1, int(settings.source_default_sync_interval_hours))


def normalize_sync_interval_hours(value: int | None) -> int:
    if value is None:
        return default_sync_interval_hours()
    return max(1, int(value))


def compute_next_sync_at(*, interval_hours: int, from_time: datetime | None = None) -> datetime:
    base_time = from_time or utcnow()
    return base_time + timedelta(hours=max(1, interval_hours))


def apply_source_schedule_defaults(source: JobSource, *, from_time: datetime | None = None) -> None:
    source.sync_interval_hours = normalize_sync_interval_hours(source.sync_interval_hours)
    if not source.active or not source.auto_sync_enabled:
        source.next_sync_at = None
        return
    source.next_sync_at = compute_next_sync_at(
        interval_hours=source.sync_interval_hours,
        from_time=from_time,
    )


def mark_source_synced(source: JobSource, *, synced_at: datetime | None = None) -> None:
    completed_at = synced_at or utcnow()
    source.last_synced_at = completed_at
    source.sync_lease_expires_at = None
    if source.active and source.auto_sync_enabled:
        source.next_sync_at = compute_next_sync_at(
            interval_hours=source.sync_interval_hours,
            from_time=completed_at,
        )
    else:
        source.next_sync_at = None


def release_source_sync_lease(session: Session, *, source_id: int) -> None:
    session.execute(
        update(JobSource)
        .where(JobSource.id == source_id)
        .values(sync_lease_expires_at=None),
    )
    session.flush()


def acquire_source_sync_lease(session: Session, *, source_id: int) -> bool:
    settings = get_settings()
    now = utcnow()
    lease_expires_at = now + timedelta(seconds=max(1, settings.source_sync_lease_seconds))
    result = session.execute(
        update(JobSource)
        .where(
            JobSource.id == source_id,
            (JobSource.sync_lease_expires_at.is_(None) | (JobSource.sync_lease_expires_at <= now)),
        )
        .values(sync_lease_expires_at=lease_expires_at),
    )
    session.flush()
    return bool(result.rowcount)


def select_due_source_ids(session: Session, *, now: datetime | None = None) -> list[int]:
    current_time = now or utcnow()
    return session.scalars(
        select(JobSource.id)
        .where(
            JobSource.active.is_(True),
            JobSource.auto_sync_enabled.is_(True),
            JobSource.next_sync_at.is_not(None),
            JobSource.next_sync_at <= current_time,
            (JobSource.sync_lease_expires_at.is_(None) | (JobSource.sync_lease_expires_at <= current_time)),
        )
        .order_by(JobSource.next_sync_at.asc(), JobSource.id.asc())
    ).all()
