from app.domains.accounts.service import ensure_account
from app.domains.applications.models import ApplicationEvent, ApplicationRun
from app.domains.jobs.models import ApplyTarget, Job


def test_action_needed_route_returns_blocked_runs_with_artifacts(auth_client, db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    job = Job(
        account_id=account.id,
        canonical_key="acme-linkedin-software-engineer-i",
        company_name="Acme",
        title="Software Engineer I",
        location="Remote",
        status="action_needed",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    apply_target = ApplyTarget(
        job_id=job.id,
        target_type="linkedin_easy_apply",
        destination_url="https://www.linkedin.com/jobs/view/123",
        is_preferred=True,
        metadata_json={"linkedin_job_id": "123"},
    )
    db_session.add(apply_target)
    db_session.commit()
    db_session.refresh(apply_target)

    run = ApplicationRun(
        account_id=account.id,
        job_id=job.id,
        apply_target_id=apply_target.id,
        status="cooldown_required",
    )
    db_session.add(run)
    db_session.flush()
    db_session.add(
        ApplicationEvent(
            application_run_id=run.id,
            event_type="cooldown_required",
            payload={
                "blocker_type": "cooldown_required",
                "step": "review",
                "message": "LinkedIn asked us to slow down.",
                "artifacts": [{"kind": "page_html", "path": "/tmp/openjob/run-1/page_html.html"}],
            },
        )
    )
    db_session.commit()

    response = auth_client.get("/api/applications/action-needed")

    assert response.status_code == 200
    assert response.json() == [
        {
            "application_run_id": run.id,
            "job_id": job.id,
            "company_name": "Acme",
            "title": "Software Engineer I",
            "target_type": "linkedin_easy_apply",
            "run_status": "cooldown_required",
            "blocker_type": "cooldown_required",
            "last_step": "review",
            "message": "LinkedIn asked us to slow down.",
            "artifact_paths": ["/tmp/openjob/run-1/page_html.html"],
        }
    ]
