from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app


def test_create_app_bootstraps_sqlite_schema_when_missing(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "startup-ready.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        health_response = client.get("/api/health")
        login_response = client.post(
            "/api/auth/login",
            json={"email": "owner@example.com", "password": "changeme"},
        )
        sources_response = client.get("/api/sources")

    assert health_response.status_code == 200
    assert login_response.status_code == 200
    assert sources_response.status_code == 200
    assert sources_response.json() == []
