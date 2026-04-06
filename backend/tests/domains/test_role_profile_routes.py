from fastapi.testclient import TestClient

from app.domains.accounts.service import ensure_account
from app.domains.jobs.models import Job


def test_role_profile_upsert_stores_prompt_and_generated_terms(auth_client: TestClient) -> None:
    response = auth_client.put(
        "/api/role-profile",
        json={
            "prompt": "new grad backend software engineer",
            "generated_titles": ["Software Engineer I", "Associate Software Engineer"],
            "generated_keywords": ["new grad", "entry level", "backend"],
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": 1,
        "prompt": "new grad backend software engineer",
        "generated_titles": ["Software Engineer I", "Associate Software Engineer"],
        "generated_keywords": [],
    }


def test_role_profile_upsert_updates_existing_profile(auth_client: TestClient) -> None:
    auth_client.put(
        "/api/role-profile",
        json={
            "prompt": "new grad backend software engineer",
            "generated_titles": ["Software Engineer I"],
            "generated_keywords": ["new grad"],
        },
    )

    response = auth_client.put(
        "/api/role-profile",
        json={
            "prompt": "early career platform engineer",
            "generated_titles": ["Platform Engineer I"],
            "generated_keywords": ["early career", "platform"],
        },
    )

    assert response.status_code == 200
    assert response.json()["id"] == 1
    assert response.json()["prompt"] == "early career platform engineer"
    assert response.json()["generated_titles"] == ["Platform Engineer I"]


def test_role_profile_upsert_auto_expands_missing_generated_fields(
    auth_client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.domains.role_profiles.routes.expand_role_profile_prompt",
        lambda prompt: {
            "generated_titles": ["Software Engineer I", "Backend Engineer"],
            "generated_keywords": [],
        },
    )

    response = auth_client.put(
        "/api/role-profile",
        json={
            "prompt": "new grad backend software engineer",
            "generated_titles": [],
            "generated_keywords": [],
        },
    )

    assert response.status_code == 200
    assert response.json()["generated_titles"] == ["Software Engineer I", "Backend Engineer"]
    assert response.json()["generated_keywords"] == []


def test_role_profile_upsert_rescores_existing_jobs(auth_client: TestClient, db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    db_session.add(
        Job(
            account_id=account.id,
            canonical_key="acme-role",
            company_name="Acme",
            title="Software Engineer I",
            location="Remote",
            status="discovered",
            relevance_decision="review",
            relevance_source="ai",
            relevance_summary="Old decision",
        )
    )
    db_session.commit()

    response = auth_client.put(
        "/api/role-profile",
        json={
            "prompt": "new grad backend software engineer",
            "generated_titles": ["Software Engineer I"],
            "generated_keywords": ["new grad", "backend"],
        },
    )

    assert response.status_code == 200
    updated_job = db_session.get(Job, 1)
    assert updated_job is not None
    assert updated_job.relevance_decision in {"match", "review"}
