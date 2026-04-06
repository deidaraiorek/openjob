from fastapi.testclient import TestClient


def test_create_source_persists_source_settings(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/api/sources",
        json={
            "source_key": "greenhouse-main",
            "source_type": "greenhouse_board",
            "name": "Greenhouse Main",
            "base_url": "https://boards.greenhouse.io/example",
            "settings": {"board_token": "example"},
            "active": True,
        },
    )

    assert response.status_code == 201
    assert response.json() == {
        "id": 1,
        "source_key": "greenhouse-main",
        "source_type": "greenhouse_board",
        "name": "Greenhouse Main",
        "base_url": "https://boards.greenhouse.io/example",
        "settings": {"board_token": "example"},
        "active": True,
    }


def test_duplicate_source_key_is_rejected_for_same_account(auth_client: TestClient) -> None:
    payload = {
        "source_key": "greenhouse-main",
        "source_type": "greenhouse_board",
        "name": "Greenhouse Main",
        "base_url": "https://boards.greenhouse.io/example",
        "settings": {"board_token": "example"},
        "active": True,
    }

    first_response = auth_client.post("/api/sources", json=payload)
    second_response = auth_client.post("/api/sources", json=payload)

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == "Source key already exists for this account"


def test_sync_source_route_returns_summary(
    auth_client: TestClient,
    monkeypatch,
) -> None:
    payload = {
        "source_key": "greenhouse-main",
        "source_type": "greenhouse_board",
        "name": "Greenhouse Main",
        "base_url": "https://boards.greenhouse.io/example",
        "settings": {"board_token": "example"},
        "active": True,
    }
    create_response = auth_client.post("/api/sources", json=payload)
    source_id = create_response.json()["id"]

    def fake_sync_source(session, source_id, raw_payload=None):
        return {"processed": 8, "created": 3, "updated": 5}

    monkeypatch.setattr("app.domains.sources.routes.sync_source", fake_sync_source)

    response = auth_client.post(f"/api/sources/{source_id}/sync")

    assert response.status_code == 200
    assert response.json() == {
        "source_id": source_id,
        "source_key": "greenhouse-main",
        "source_type": "greenhouse_board",
        "processed": 8,
        "created": 3,
        "updated": 5,
    }


def test_update_source_persists_edited_values(auth_client: TestClient) -> None:
    create_response = auth_client.post(
        "/api/sources",
        json={
            "source_key": "simplify-new-grad",
            "source_type": "github_curated",
            "name": "SimplifyJobs New Grad",
            "base_url": "https://github.com/SimplifyJobs/New-Grad-Positions/blob/dev/README.md",
            "settings": {},
            "active": True,
        },
    )
    source_id = create_response.json()["id"]

    response = auth_client.put(
        f"/api/sources/{source_id}",
        json={
            "source_key": "simplify-new-grad",
            "source_type": "github_curated",
            "name": "SimplifyJobs New Grad",
            "base_url": "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/README.md",
            "settings": {"note": "raw markdown"},
            "active": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["base_url"] == "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/README.md"
    assert response.json()["settings"] == {"note": "raw markdown"}


def test_sync_source_route_returns_validation_error_for_invalid_source_config(
    auth_client: TestClient,
    monkeypatch,
) -> None:
    create_response = auth_client.post(
        "/api/sources",
        json={
            "source_key": "bad-greenhouse",
            "source_type": "greenhouse_board",
            "name": "Bad Greenhouse",
            "base_url": "",
            "settings": {},
            "active": True,
        },
    )
    source_id = create_response.json()["id"]

    def fake_sync_source(session, source_id, raw_payload=None):
        raise ValueError("Greenhouse sources need a valid board URL or settings.board_token.")

    monkeypatch.setattr("app.domains.sources.routes.sync_source", fake_sync_source)

    response = auth_client.post(f"/api/sources/{source_id}/sync")

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Greenhouse sources need a valid board URL or settings.board_token."
    }
