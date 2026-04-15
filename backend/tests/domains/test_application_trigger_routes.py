from app.domains.accounts.service import ensure_account
from app.domains.jobs.models import ApplyTarget, Job


def test_trigger_application_run_uses_standard_service(
    auth_client,
    db_session,
    monkeypatch,
) -> None:
    account = ensure_account(db_session, "owner@example.com")
    job = Job(
        account_id=account.id,
        canonical_key="acme-greenhouse-software-engineer-i",
        company_name="Acme",
        title="Software Engineer I",
        location="Remote",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    db_session.add(
        ApplyTarget(
            job_id=job.id,
            target_type="greenhouse_apply",
            destination_url="https://boards.greenhouse.io/acme/jobs/123",
            is_preferred=True,
            metadata_json={"board_token": "acme", "job_post_id": "123"},
        )
    )
    db_session.commit()

    queued: list[tuple[int, str]] = []

    def fake_enqueue(job_id: int, account_email: str) -> None:
            queued.append((job_id, account_email))

    monkeypatch.setattr("app.domains.applications.routes.enqueue_application_run", fake_enqueue)

    response = auth_client.post(f"/api/applications/jobs/{job.id}/run")

    assert response.status_code == 200
    assert response.json() == {
        "application_run_id": 0,
        "status": "queued",
        "answer_entry_ids": [],
        "created_question_task_ids": [],
    }
    assert queued == [(job.id, "owner@example.com")]


def test_trigger_application_run_uses_linkedin_service(
    auth_client,
    db_session,
    monkeypatch,
) -> None:
    account = ensure_account(db_session, "owner@example.com")
    job = Job(
        account_id=account.id,
        canonical_key="acme-linkedin-software-engineer-i",
        company_name="Acme",
        title="Software Engineer I",
        location="Remote",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    db_session.add(
        ApplyTarget(
            job_id=job.id,
            target_type="linkedin_easy_apply",
            destination_url="https://www.linkedin.com/jobs/view/123",
            is_preferred=True,
            metadata_json={"linkedin_job_id": "123"},
        )
    )
    db_session.commit()

    queued: list[tuple[int, str]] = []

    def fake_enqueue(job_id: int, account_email: str) -> None:
            queued.append((job_id, account_email))

    monkeypatch.setattr("app.domains.applications.routes.enqueue_application_run", fake_enqueue)

    response = auth_client.post(f"/api/applications/jobs/{job.id}/run")

    assert response.status_code == 200
    assert response.json() == {
        "application_run_id": 0,
        "status": "queued",
        "answer_entry_ids": [],
        "created_question_task_ids": [],
    }
    assert queued == [(job.id, "owner@example.com")]


def test_trigger_application_run_rejects_platforms_that_are_not_supported_yet(
    auth_client,
    db_session,
) -> None:
    account = ensure_account(db_session, "owner@example.com")
    job = Job(
        account_id=account.id,
        canonical_key="acme-workday-software-engineer",
        company_name="Acme",
        title="Software Engineer",
        location="Remote",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    db_session.add(
        ApplyTarget(
            job_id=job.id,
            target_type="external_link",
            destination_url="https://acme.wd1.myworkdaysite.com/recruiting/acme/job/123",
            is_preferred=True,
            metadata_json={},
        )
    )
    db_session.commit()

    response = auth_client.post(f"/api/applications/jobs/{job.id}/run")

    assert response.status_code == 422
    assert "Workday link is recognized" in response.json()["detail"]


def test_trigger_application_run_rejects_recognized_external_links_until_upgraded(
    auth_client,
    db_session,
) -> None:
    account = ensure_account(db_session, "owner@example.com")
    job = Job(
        account_id=account.id,
        canonical_key="acme-lever-external-link",
        company_name="Acme",
        title="Software Engineer",
        location="Remote",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    db_session.add(
        ApplyTarget(
            job_id=job.id,
            target_type="external_link",
            destination_url="https://jobs.lever.co/acme/lever-123/apply",
            is_preferred=True,
            metadata_json={"origin": "github_curated"},
        )
    )
    db_session.commit()

    response = auth_client.post(f"/api/applications/jobs/{job.id}/run")

    assert response.status_code == 422
    assert "generic external target still needs a target upgrade" in response.json()["detail"]


def test_trigger_application_run_requires_application_accounts_when_target_demands_it(
    auth_client,
    db_session,
) -> None:
    account = ensure_account(db_session, "owner@example.com")
    job = Job(
        account_id=account.id,
        canonical_key="acme-linkedin-account-required",
        company_name="Acme",
        title="Software Engineer",
        location="Remote",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    db_session.add(
        ApplyTarget(
            job_id=job.id,
            target_type="linkedin_easy_apply",
            destination_url="https://www.linkedin.com/jobs/view/123",
            is_preferred=True,
            metadata_json={"linkedin_job_id": "123", "credential_policy": "tenant_required"},
        )
    )
    db_session.commit()

    response = auth_client.post(f"/api/applications/jobs/{job.id}/run")

    assert response.status_code == 422
    assert "Add an application account for LinkedIn" in response.json()["detail"]
