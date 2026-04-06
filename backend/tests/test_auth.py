from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app


def build_client() -> TestClient:
    get_settings.cache_clear()
    return TestClient(create_app())


def test_login_sets_session_and_returns_owner_email() -> None:
    client = build_client()

    response = client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": "changeme"},
    )

    assert response.status_code == 200
    assert response.json() == {"authenticated": True, "email": "owner@example.com"}
    assert "openjob_session" in response.cookies


def test_invalid_credentials_do_not_create_session() -> None:
    client = build_client()

    response = client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": "nope"},
    )

    assert response.status_code == 401
    assert response.json() == {"authenticated": False, "email": None}


def test_session_endpoint_requires_authentication() -> None:
    client = build_client()

    response = client.get("/api/auth/session")

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


def test_session_endpoint_returns_owner_after_login() -> None:
    client = build_client()
    client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": "changeme"},
    )

    response = client.get("/api/auth/session")

    assert response.status_code == 200
    assert response.json() == {"authenticated": True, "email": "owner@example.com"}
