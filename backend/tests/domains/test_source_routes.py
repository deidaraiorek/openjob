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
        "auto_sync_enabled": True,
        "sync_interval_hours": 6,
        "last_synced_at": None,
        "next_sync_at": response.json()["next_sync_at"],
    }
    assert response.json()["next_sync_at"] is not None


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
        return {
            "processed": 8,
            "created": 3,
            "updated": 5,
            "pending_title_screening": 0,
            "pending_full_relevance": 0,
        }

    monkeypatch.setattr("app.domains.sources.routes.sync_source", fake_sync_source)

    response = auth_client.post(f"/api/sources/{source_id}/sync")

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "source_id": source_id,
        "source_key": "greenhouse-main",
        "source_type": "greenhouse_board",
        "processed": 8,
        "created": 3,
        "updated": 5,
        "pending_title_screening": 0,
        "pending_full_relevance": 0,
        "last_synced_at": payload["last_synced_at"],
        "next_sync_at": payload["next_sync_at"],
    }
    assert payload["last_synced_at"] is not None
    assert payload["next_sync_at"] is not None


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
    assert response.json()["auto_sync_enabled"] is True
    assert response.json()["sync_interval_hours"] == 6


def test_delete_source_removes_source(auth_client: TestClient) -> None:
    create_response = auth_client.post(
        "/api/sources",
        json={
            "source_key": "to-delete",
            "source_type": "github_curated",
            "name": "Delete Me",
            "base_url": "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/README.md",
            "settings": {},
            "active": True,
        },
    )
    source_id = create_response.json()["id"]

    delete_response = auth_client.delete(f"/api/sources/{source_id}")
    list_response = auth_client.get("/api/sources")

    assert delete_response.status_code == 204
    assert list_response.status_code == 200
    assert list_response.json() == []


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


def test_sync_source_route_rejects_overlapping_sync_requests(auth_client: TestClient, monkeypatch) -> None:
    create_response = auth_client.post(
        "/api/sources",
        json={
            "source_key": "busy-sync",
            "source_type": "greenhouse_board",
            "name": "Busy Sync",
            "base_url": "https://boards.greenhouse.io/example",
            "settings": {},
            "active": True,
        },
    )
    source_id = create_response.json()["id"]

    monkeypatch.setattr("app.domains.sources.routes.acquire_source_sync_lease", lambda session, source_id: False)

    response = auth_client.post(f"/api/sources/{source_id}/sync")

    assert response.status_code == 409
    assert response.json() == {
        "detail": "This source is already syncing. Wait for it to finish before starting another run."
    }


def test_update_source_persists_auto_sync_fields(auth_client: TestClient) -> None:
    create_response = auth_client.post(
        "/api/sources",
        json={
            "source_key": "auto-sync-source",
            "source_type": "greenhouse_board",
            "name": "Auto Sync Source",
            "base_url": "https://boards.greenhouse.io/example",
            "settings": {},
            "active": True,
        },
    )
    source_id = create_response.json()["id"]

    response = auth_client.put(
        f"/api/sources/{source_id}",
        json={
            "source_key": "auto-sync-source",
            "source_type": "greenhouse_board",
            "name": "Auto Sync Source",
            "base_url": "https://boards.greenhouse.io/example",
            "settings": {},
            "active": True,
            "auto_sync_enabled": False,
            "sync_interval_hours": 12,
        },
    )

    assert response.status_code == 200
    assert response.json()["auto_sync_enabled"] is False
    assert response.json()["sync_interval_hours"] == 12
    assert response.json()["next_sync_at"] is None


def test_sync_source_route_rejects_inactive_sources(auth_client: TestClient) -> None:
    create_response = auth_client.post(
        "/api/sources",
        json={
            "source_key": "inactive-source",
            "source_type": "greenhouse_board",
            "name": "Inactive Source",
            "base_url": "https://boards.greenhouse.io/example",
            "settings": {},
            "active": False,
        },
    )
    source_id = create_response.json()["id"]

    response = auth_client.post(f"/api/sources/{source_id}/sync")

    assert response.status_code == 400
    assert response.json() == {"detail": "Inactive sources must be reactivated before syncing."}


def test_manual_sync_updates_source_schedule(auth_client: TestClient, monkeypatch) -> None:
    create_response = auth_client.post(
        "/api/sources",
        json={
            "source_key": "scheduled-source",
            "source_type": "greenhouse_board",
            "name": "Scheduled Source",
            "base_url": "https://boards.greenhouse.io/example",
            "settings": {},
            "active": True,
            "sync_interval_hours": 3,
        },
    )
    source_id = create_response.json()["id"]

    monkeypatch.setattr(
        "app.domains.sources.routes.sync_source",
        lambda session, source_id, raw_payload=None: {
            "processed": 1,
            "created": 1,
            "updated": 0,
            "pending_title_screening": 0,
            "pending_full_relevance": 0,
        },
    )

    response = auth_client.post(f"/api/sources/{source_id}/sync")
    sources_response = auth_client.get("/api/sources")
    source_payload = next(item for item in sources_response.json() if item["id"] == source_id)

    assert response.status_code == 200
    assert source_payload["last_synced_at"] is not None
    assert source_payload["next_sync_at"] is not None
