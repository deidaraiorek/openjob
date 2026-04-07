from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


SQLITE_BUSY_TIMEOUT_MS = 30_000


def _engine_options(database_url: str) -> dict[str, object]:
    options: dict[str, object] = {
        "future": True,
        "pool_pre_ping": True,
    }

    if database_url.startswith("sqlite"):
        options["connect_args"] = {
            "check_same_thread": False,
            "timeout": SQLITE_BUSY_TIMEOUT_MS / 1000,
        }

    return options


def _configure_sqlite_connection(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.execute("PRAGMA journal_mode = WAL")
            cursor.execute("PRAGMA synchronous = NORMAL")
        finally:
            cursor.close()


@lru_cache
def get_engine(database_url: str | None = None) -> Engine:
    resolved_url = database_url or get_settings().database_url
    engine = create_engine(resolved_url, **_engine_options(resolved_url))
    if resolved_url.startswith("sqlite"):
        _configure_sqlite_connection(engine)
    return engine


@lru_cache
def get_session_factory(database_url: str | None = None) -> sessionmaker[Session]:
    return sessionmaker(
        bind=get_engine(database_url),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        future=True,
    )


def get_db_session() -> Generator[Session, None, None]:
    session_factory = get_session_factory()
    with session_factory() as session:
        yield session
