from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.domains.logs.models import SystemEvent


def log_system_event(
    session: Session,
    *,
    event_type: str,
    source: str,
    payload: dict[str, Any] | None = None,
    account_id: int | None = None,
) -> None:
    session.add(
        SystemEvent(
            account_id=account_id,
            event_type=event_type,
            source=source,
            payload=payload or {},
        )
    )
    session.flush()
