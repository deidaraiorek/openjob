from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.domains.accounts.service import ensure_account
from app.domains.applications.models import ApplicationRun
from app.domains.jobs.models import ApplyTarget, Job
from app.domains.questions.fingerprints import fingerprint_question
from app.domains.questions.models import AnswerEntry, QuestionTemplate
from app.tasks.applications import run_application


def test_run_application_task_returns_retry_status_when_submit_fails(
    monkeypatch,
    db_session,
    db_engine,
) -> None:
    account = ensure_account(db_session, "owner@example.com")
    job = Job(
        account_id=account.id,
        canonical_key="acme-sre-i",
        company_name="Acme",
        title="SRE I",
        location="Remote",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    template = QuestionTemplate(
        account_id=account.id,
        fingerprint=fingerprint_question("Portfolio URL", "input_text", []),
        prompt_text="Portfolio URL",
        field_type="input_text",
        option_labels=[],
    )
    answer = AnswerEntry(
        account_id=account.id,
        question_template=template,
        label="Portfolio",
        answer_text="https://example.com",
    )
    apply_target = ApplyTarget(
        job_id=job.id,
        target_type="greenhouse_apply",
        destination_url="https://boards.greenhouse.io/acme/jobs/999",
        is_preferred=True,
        metadata_json={"board_token": "acme", "job_post_id": "999", "api_key": "secret"},
    )
    db_session.add_all([template, answer, apply_target])
    db_session.commit()

    monkeypatch.setattr(
        "app.domains.applications.service._default_fetch_questions",
        lambda _: {
            "questions": [
                {
                    "label": "Portfolio URL",
                    "required": True,
                    "fields": [{"name": "portfolio", "type": "input_text", "values": []}],
                }
            ]
        },
    )

    from app.domains.applications.retry_policy import RetryableApplyError

    monkeypatch.setattr(
        "app.domains.applications.service._default_submit",
        lambda *_: (_ for _ in ()).throw(RetryableApplyError("temporary upstream timeout")),
    )
    monkeypatch.setattr(
        "app.tasks.applications.get_session_factory",
        lambda: sessionmaker(
            bind=db_engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            future=True,
        ),
    )

    result = run_application.run(job.id, account_email="owner@example.com")

    run = db_session.scalar(select(ApplicationRun).where(ApplicationRun.id == result["application_run_id"]))

    assert result["status"] == "retry_scheduled"
    assert run is not None
    assert run.status == "retry_scheduled"
