from datetime import UTC, datetime, timedelta

from app.domains.accounts.service import ensure_account
from app.domains.sources.models import JobSource
from app.tasks.discovery import enqueue_due_source_syncs_now


def test_enqueue_due_source_syncs_only_enqueues_due_active_auto_sync_sources(db_session, monkeypatch) -> None:
    account = ensure_account(db_session, "owner@example.com")
    now = datetime.now(UTC)
    due_source = JobSource(
        account_id=account.id,
        source_key="due",
        source_type="greenhouse_board",
        name="Due",
        base_url="https://boards.greenhouse.io/due",
        settings_json={},
        active=True,
        auto_sync_enabled=True,
        sync_interval_hours=6,
        next_sync_at=now - timedelta(minutes=5),
    )
    future_source = JobSource(
        account_id=account.id,
        source_key="future",
        source_type="greenhouse_board",
        name="Future",
        base_url="https://boards.greenhouse.io/future",
        settings_json={},
        active=True,
        auto_sync_enabled=True,
        sync_interval_hours=6,
        next_sync_at=now + timedelta(minutes=5),
    )
    disabled_source = JobSource(
        account_id=account.id,
        source_key="disabled",
        source_type="greenhouse_board",
        name="Disabled",
        base_url="https://boards.greenhouse.io/disabled",
        settings_json={},
        active=True,
        auto_sync_enabled=False,
        sync_interval_hours=6,
        next_sync_at=now - timedelta(minutes=5),
    )
    inactive_source = JobSource(
        account_id=account.id,
        source_key="inactive",
        source_type="greenhouse_board",
        name="Inactive",
        base_url="https://boards.greenhouse.io/inactive",
        settings_json={},
        active=False,
        auto_sync_enabled=True,
        sync_interval_hours=6,
        next_sync_at=now - timedelta(minutes=5),
    )
    db_session.add_all([due_source, future_source, disabled_source, inactive_source])
    db_session.commit()

    queued_source_ids: list[int] = []

    class DelayRecorder:
        def delay(self, source_id: int) -> None:
            queued_source_ids.append(source_id)

    monkeypatch.setattr("app.tasks.discovery.sync_source_task", DelayRecorder())

    enqueued = enqueue_due_source_syncs_now(db_session)

    assert enqueued == 1
    assert queued_source_ids == [due_source.id]
