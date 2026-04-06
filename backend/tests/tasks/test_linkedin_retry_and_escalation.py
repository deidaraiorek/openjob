from pathlib import Path

from sqlalchemy import select

from app.config import Settings
from app.domains.accounts.service import ensure_account
from app.domains.applications.models import ApplicationEvent, ApplicationRun
from app.domains.jobs.models import ApplyTarget, Job
from app.domains.questions.fingerprints import ApplyQuestion
from app.integrations.linkedin.apply import (
    LinkedInInspection,
    LinkedInSubmission,
    execute_linkedin_application_run,
)
from app.integrations.linkedin.blockers import LinkedInAutomationError


def test_linkedin_apply_records_cooldown_artifacts(db_session, tmp_path) -> None:
    account = ensure_account(db_session, "owner@example.com")
    job = Job(
        account_id=account.id,
        canonical_key="linkedin-acme-software-engineer-i",
        company_name="Acme",
        title="Software Engineer I",
        location="Remote",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    target = ApplyTarget(
        job_id=job.id,
        target_type="linkedin_easy_apply",
        destination_url="https://www.linkedin.com/jobs/view/123",
        is_preferred=True,
        metadata_json={"linkedin_job_id": "123"},
    )
    db_session.add(target)
    db_session.commit()

    result = execute_linkedin_application_run(
        db_session,
        account=account,
        job_id=job.id,
        inspect_flow=lambda *_: (_ for _ in ()).throw(
            LinkedInAutomationError(
                code="daily_limit_reached",
                step="review",
                message="LinkedIn asked us to slow down.",
                artifacts={"page_html": "<html>too many applications</html>"},
                page_text="You've exceeded the daily application limit. Try again tomorrow.",
            )
        ),
        settings=Settings(
            database_url="sqlite://",
            redis_url="redis://localhost:6379/0",
            playwright_profile_dir=str(tmp_path / "profiles"),
            playwright_artifact_dir=str(tmp_path / "artifacts"),
            openai_api_key=None,
        ),
    )

    run = db_session.scalar(select(ApplicationRun).where(ApplicationRun.id == result.application_run_id))
    event = db_session.scalar(
        select(ApplicationEvent).where(ApplicationEvent.application_run_id == result.application_run_id)
    )

    assert result.status == "cooldown_required"
    assert run is not None
    assert run.status == "cooldown_required"
    assert event is not None
    assert event.event_type == "queued"
    latest_event = db_session.scalars(
        select(ApplicationEvent)
        .where(ApplicationEvent.application_run_id == result.application_run_id)
        .order_by(ApplicationEvent.id.asc())
    ).all()[-1]
    assert latest_event.payload["blocker_type"] == "cooldown_required"
    artifact_path = Path(latest_event.payload["artifacts"][0]["path"])
    assert artifact_path.exists()


def test_linkedin_apply_escalates_platform_changed_after_question_inspection(db_session, tmp_path) -> None:
    account = ensure_account(db_session, "owner@example.com")
    job = Job(
        account_id=account.id,
        canonical_key="linkedin-acme-backend-engineer-i",
        company_name="Acme",
        title="Backend Engineer I",
        location="Remote",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    target = ApplyTarget(
        job_id=job.id,
        target_type="linkedin_easy_apply",
        destination_url="https://www.linkedin.com/jobs/view/456",
        is_preferred=True,
        metadata_json={"linkedin_job_id": "456"},
    )
    db_session.add(target)
    db_session.commit()

    result = execute_linkedin_application_run(
        db_session,
        account=account,
        job_id=job.id,
        inspect_flow=lambda *_: LinkedInInspection(
            step="form-intake",
            questions=[
                ApplyQuestion(
                    key="portfolio",
                    prompt_text="Portfolio URL",
                    field_type="input_text",
                    required=False,
                )
            ],
        ),
        submit_flow=lambda *_: (_ for _ in ()).throw(
            LinkedInAutomationError(
                code="selector_missing",
                step="form-submit",
                message="Expected submit button selector missing.",
                artifacts={"page_html": "<html>layout drift</html>"},
            )
        ),
        settings=Settings(
            database_url="sqlite://",
            redis_url="redis://localhost:6379/0",
            playwright_profile_dir=str(tmp_path / "profiles"),
            playwright_artifact_dir=str(tmp_path / "artifacts"),
            openai_api_key=None,
        ),
    )

    run = db_session.scalar(select(ApplicationRun).where(ApplicationRun.id == result.application_run_id))

    assert result.status == "platform_changed"
    assert run is not None
    assert run.status == "platform_changed"
