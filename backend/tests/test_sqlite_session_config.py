from __future__ import annotations

from app.db.session import SQLITE_BUSY_TIMEOUT_MS, get_engine


def test_sqlite_engine_applies_busy_timeout_and_wal(tmp_path) -> None:
    database_path = tmp_path / "sqlite-config.db"
    engine = get_engine(f"sqlite:///{database_path}")

    with engine.connect() as connection:
        busy_timeout = connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one()
        journal_mode = connection.exec_driver_sql("PRAGMA journal_mode").scalar_one()
        foreign_keys = connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one()

    assert busy_timeout == SQLITE_BUSY_TIMEOUT_MS
    assert journal_mode == "wal"
    assert foreign_keys == 1
