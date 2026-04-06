from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def _engine_options(database_url: str) -> dict[str, object]:
    options: dict[str, object] = {
        "future": True,
        "pool_pre_ping": True,
    }

    if database_url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}

    return options


@lru_cache
def get_engine(database_url: str | None = None) -> Engine:
    resolved_url = database_url or get_settings().database_url
    return create_engine(resolved_url, **_engine_options(resolved_url))


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
