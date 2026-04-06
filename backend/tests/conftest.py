from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.db.models  # noqa: F401
from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app


@pytest.fixture()
def db_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def session_factory(db_engine) -> sessionmaker[Session]:
    return sessionmaker(bind=db_engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)


@pytest.fixture()
def db_session(session_factory) -> Session:
    with session_factory() as session:
        yield session


@pytest.fixture()
def client(session_factory) -> TestClient:
    app = create_app()

    def override_get_db_session():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture()
def auth_client(client: TestClient) -> TestClient:
    response = client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": "changeme"},
    )
    assert response.status_code == 200
    return client
