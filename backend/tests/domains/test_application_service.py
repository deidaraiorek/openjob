import pytest
from sqlalchemy import func, select

from app.domains.accounts.service import ensure_account
from app.domains.applications.models import ApplicationEvent, ApplicationRun
from app.domains.applications.retry_policy import ActionNeededApplyError, RetryableApplyError, TerminalApplyError
from app.domains.applications.service import execute_application_run
from app.domains.jobs.models import ApplyTarget, Job
from app.domains.questions.fingerprints import fingerprint_question
from app.domains.questions.models import AnswerEntry, QuestionTask, QuestionTemplate


def test_execute_application_run_blocks_when_required_answer_is_missing(db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    job = Job(
        account_id=account.id,
        canonical_key="acme-software-engineer-i",
        company_name="Acme",
        title="Software Engineer I",
        location="Remote",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    apply_target = ApplyTarget(
        job_id=job.id,
        target_type="greenhouse_apply",
        destination_url="https://boards.greenhouse.io/acme/jobs/123",
        is_preferred=True,
        metadata_json={"board_token": "acme", "job_post_id": "123", "api_key": "secret"},
    )
    db_session.add(apply_target)
    db_session.commit()

    question_payload = {
        "questions": [
            {
                "label": "LinkedIn profile URL",
                "required": True,
                "fields": [{"name": "linkedin", "type": "input_text", "values": []}],
            }
        ]
    }

    result = execute_application_run(
        db_session,
        account=account,
        job_id=job.id,
        fetch_questions=lambda _: question_payload,
        submit_application=lambda *_: {"status": "submitted"},
    )

    run = db_session.scalar(select(ApplicationRun).where(ApplicationRun.id == result.application_run_id))
    task_count = db_session.scalar(select(func.count(QuestionTask.id)))
    event_types = db_session.scalars(
        select(ApplicationEvent.event_type).where(ApplicationEvent.application_run_id == run.id)
    ).all()

    assert result.status == "blocked_missing_answer"
    assert run is not None
    assert run.status == "blocked_missing_answer"
    assert task_count == 1
    assert "blocked_missing_answer" in event_types


def test_execute_application_run_submits_when_answers_exist_and_logs_redacted_payload(db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    job = Job(
        account_id=account.id,
        canonical_key="acme-backend-engineer-i",
        company_name="Acme",
        title="Backend Engineer I",
        location="Remote",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    template = QuestionTemplate(
        account_id=account.id,
        fingerprint=fingerprint_question("LinkedIn profile URL", "input_text", []),
        prompt_text="LinkedIn profile URL",
        field_type="input_text",
        option_labels=[],
    )
    db_session.add(template)
    db_session.commit()
    db_session.refresh(template)

    answer = AnswerEntry(
        account_id=account.id,
        question_template_id=template.id,
        label="LinkedIn URL",
        answer_text="https://linkedin.com/in/example",
    )
    apply_target = ApplyTarget(
        job_id=job.id,
        target_type="greenhouse_apply",
        destination_url="https://boards.greenhouse.io/acme/jobs/456",
        is_preferred=True,
        metadata_json={"board_token": "acme", "job_post_id": "456", "api_key": "secret"},
    )
    db_session.add_all([answer, apply_target])
    db_session.commit()

    question_payload = {
        "questions": [
            {
                "label": "LinkedIn profile URL",
                "required": True,
                "fields": [{"name": "linkedin", "type": "input_text", "values": []}],
            }
        ]
    }

    result = execute_application_run(
        db_session,
        account=account,
        job_id=job.id,
        fetch_questions=lambda _: question_payload,
        submit_application=lambda *_: {"status": "ok", "submission_id": "abc123"},
    )

    run = db_session.scalar(select(ApplicationRun).where(ApplicationRun.id == result.application_run_id))
    submitted_event = db_session.scalar(
        select(ApplicationEvent)
        .where(
            ApplicationEvent.application_run_id == run.id,
            ApplicationEvent.event_type == "submitted",
        )
    )

    assert result.status == "submitted"
    assert result.answer_entry_ids == [answer.id]
    assert run is not None
    assert run.status == "submitted"
    assert submitted_event is not None
    assert submitted_event.payload["answer_entry_ids"] == [answer.id]
    assert submitted_event.payload["submission_payload"]["linkedin"] == "<redacted>"
    assert submitted_event.payload["submit_response"]["submission_id"] == "<redacted>"


def test_execute_application_run_marks_retryable_failures(db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    job = Job(
        account_id=account.id,
        canonical_key="acme-platform-engineer-i",
        company_name="Acme",
        title="Platform Engineer I",
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
    db_session.add(template)
    db_session.commit()
    db_session.refresh(template)

    answer = AnswerEntry(
        account_id=account.id,
        question_template_id=template.id,
        label="Portfolio URL",
        answer_text="https://example.com",
    )
    apply_target = ApplyTarget(
        job_id=job.id,
        target_type="greenhouse_apply",
        destination_url="https://boards.greenhouse.io/acme/jobs/789",
        is_preferred=True,
        metadata_json={"board_token": "acme", "job_post_id": "789", "api_key": "secret"},
    )
    db_session.add_all([answer, apply_target])
    db_session.commit()

    question_payload = {
        "questions": [
            {
                "label": "Portfolio URL",
                "required": True,
                "fields": [{"name": "portfolio", "type": "input_text", "values": []}],
            }
        ]
    }

    retry_result = execute_application_run(
        db_session,
        account=account,
        job_id=job.id,
        fetch_questions=lambda _: question_payload,
        submit_application=lambda *_: (_ for _ in ()).throw(RetryableApplyError("timeout")),
    )
    action_result = execute_application_run(
        db_session,
        account=account,
        job_id=job.id,
        fetch_questions=lambda _: question_payload,
        submit_application=lambda *_: (_ for _ in ()).throw(ActionNeededApplyError("captcha required")),
    )

    assert retry_result.status == "retry_scheduled"
    assert action_result.status == "action_needed"


def test_execute_application_run_rejects_targets_that_are_not_ready(db_session) -> None:
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

    with pytest.raises(TerminalApplyError, match="Workday link is recognized"):
        execute_application_run(
            db_session,
            account=account,
            job_id=job.id,
            fetch_questions=lambda _: {"questions": []},
            submit_application=lambda *_: {"status": "submitted"},
        )


def test_execute_application_run_passes_lever_company_slug_to_question_fetch(db_session, monkeypatch) -> None:
    account = ensure_account(db_session, "owner@example.com")
    job = Job(
        account_id=account.id,
        canonical_key="weride-software-engineer-algorithm",
        company_name="WeRide",
        title="New Grads 2026 - Software Engineer - Algorithm",
        location="Remote",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    apply_target = ApplyTarget(
        job_id=job.id,
        target_type="lever_apply",
        destination_url="https://jobs.lever.co/weride/posting-123/apply",
        is_preferred=True,
        metadata_json={
            "posting_id": "posting-123",
            "company_slug": "weride",
            "api_key": "secret",
        },
    )
    db_session.add(apply_target)
    db_session.commit()

    fetch_calls: list[tuple[str, str | None]] = []

    def fake_fetch_question_payload(posting_id: str, company_slug: str | None = None) -> dict:
        fetch_calls.append((posting_id, company_slug))
        return {}

    monkeypatch.setattr(
        "app.domains.applications.service.lever_apply.fetch_question_payload",
        fake_fetch_question_payload,
    )

    result = execute_application_run(
        db_session,
        account=account,
        job_id=job.id,
        submit_application=lambda *_: {"status": "submitted"},
    )

    assert result.status == "submitted"
    assert fetch_calls == [("posting-123", "weride")]


def test_execute_application_run_passes_lever_company_slug_to_submit(db_session, monkeypatch) -> None:
    account = ensure_account(db_session, "owner@example.com")
    job = Job(
        account_id=account.id,
        canonical_key="weride-software-engineer-general",
        company_name="WeRide",
        title="New Grads 2026 - General Software Engineer",
        location="Remote",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    apply_target = ApplyTarget(
        job_id=job.id,
        target_type="lever_apply",
        destination_url="https://jobs.lever.co/weride/posting-123/apply",
        is_preferred=True,
        metadata_json={
            "posting_id": "posting-123",
            "company_slug": "weride",
        },
    )
    db_session.add(apply_target)
    db_session.commit()

    template = QuestionTemplate(
        account_id=account.id,
        fingerprint=fingerprint_question("Full name", "text", []),
        prompt_text="Full name",
        field_type="text",
        option_labels=[],
    )
    db_session.add(template)
    db_session.commit()
    db_session.refresh(template)

    answer = AnswerEntry(
        account_id=account.id,
        question_template_id=template.id,
        label="Full name",
        answer_text="Dang Pham",
    )
    db_session.add(answer)
    db_session.commit()

    monkeypatch.setattr(
        "app.domains.applications.service.lever_apply.fetch_question_payload",
        lambda posting_id, company_slug=None: {
            "personalInformation": [
                {"name": "name", "text": "Full name", "type": "text", "required": True},
            ]
        },
    )

    submit_calls: list[tuple[str, str | None, dict[str, object]]] = []

    def fake_submit_application(posting_id: str, submission_payload: dict[str, object], company_slug: str | None = None):
        submit_calls.append((posting_id, company_slug, submission_payload))
        return {"status": "submitted"}

    monkeypatch.setattr(
        "app.domains.applications.service.lever_apply.submit_application",
        fake_submit_application,
    )

    result = execute_application_run(
        db_session,
        account=account,
        job_id=job.id,
    )

    assert result.status == "submitted"
    assert submit_calls == [
        (
            "posting-123",
            "weride",
            {"fields": [{"name": "name", "value": "Dang Pham"}]},
        )
    ]
