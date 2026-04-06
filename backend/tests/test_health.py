from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app


def test_health_check_returns_status() -> None:
    get_settings.cache_clear()
    client = TestClient(create_app())

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
