from types import SimpleNamespace

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

    def fake_execute(session, *, account, job_id, fetch_questions=None, submit_application=None):
        return SimpleNamespace(
            application_run_id=41,
            status="submitted",
            answer_entry_ids=[7],
            created_question_task_ids=[],
        )

    monkeypatch.setattr("app.domains.applications.routes.execute_application_run", fake_execute)

    response = auth_client.post(f"/api/applications/jobs/{job.id}/run")

    assert response.status_code == 200
    assert response.json() == {
        "application_run_id": 41,
        "status": "submitted",
        "answer_entry_ids": [7],
        "created_question_task_ids": [],
    }


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

    def fake_execute(session, *, account, job_id, inspect_flow=None, submit_flow=None, settings=None):
        return SimpleNamespace(
            application_run_id=52,
            status="cooldown_required",
            answer_entry_ids=[],
            created_question_task_ids=[],
        )

    monkeypatch.setattr(
        "app.domains.applications.routes.execute_linkedin_application_run",
        fake_execute,
    )

    response = auth_client.post(f"/api/applications/jobs/{job.id}/run")

    assert response.status_code == 200
    assert response.json() == {
        "application_run_id": 52,
        "status": "cooldown_required",
        "answer_entry_ids": [],
        "created_question_task_ids": [],
    }
