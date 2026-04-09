from datetime import datetime

from sqlalchemy import func, select

from app.domains.accounts.service import ensure_account
from app.domains.jobs.models import ApplyTarget, Job, JobRelevanceEvaluation, JobRelevanceTask, JobSighting
from app.domains.jobs.relevance import upsert_relevance_task
from app.domains.role_profiles.models import RoleProfile
from app.domains.sources.models import JobSource
from app.integrations.openai.job_relevance import JobRelevanceResult
from app.integrations.openai.job_title_screening import JobTitleScreeningItem, JobTitleScreeningResult
from app.tasks.job_relevance import drain_relevance_tasks_now


def _create_job_fixture(db_session):
    account = ensure_account(db_session, "owner@example.com")
    profile = RoleProfile(
        account_id=account.id,
        prompt="software engineer new grad",
        generated_titles=[],
        generated_keywords=[],
    )
    source = JobSource(
        account_id=account.id,
        source_key="greenhouse",
        source_type="greenhouse_board",
        name="Greenhouse",
        base_url="https://boards.greenhouse.io/acme",
        settings_json={"board_token": "acme"},
    )
    job = Job(
        account_id=account.id,
        canonical_key="acme-software-engineer-i-remote",
        company_name="Acme",
        title="Software Engineer I",
        location="Remote",
        status="discovered",
        relevance_decision="pending",
        relevance_source="pending_title_screening",
        relevance_summary="Waiting for AI title screening.",
    )
    sighting = JobSighting(
        job=job,
        source=source,
        external_job_id="123",
        listing_url="https://boards.greenhouse.io/acme/jobs/123",
        apply_url="https://boards.greenhouse.io/acme/jobs/123",
        raw_payload={"description": "Entry-level backend software engineering role."},
    )
    target = ApplyTarget(
        job=job,
        target_type="greenhouse_apply",
        destination_url="https://boards.greenhouse.io/acme/jobs/123",
        is_preferred=True,
        metadata_json={},
    )
    db_session.add_all([profile, source, job, sighting, target])
    db_session.commit()
    db_session.refresh(job)
    return account, profile, source, job


def test_drain_relevance_tasks_now_moves_passed_titles_to_full_relevance_pending(db_session, monkeypatch) -> None:
    account, _profile, _source, job = _create_job_fixture(db_session)
    upsert_relevance_task(
        db_session,
        account_id=account.id,
        job_id=job.id,
        phase="title_screening",
        reset_attempts=True,
    )
    db_session.commit()

    monkeypatch.setattr(
        "app.tasks.job_relevance.classify_job_titles",
        lambda *args, **kwargs: JobTitleScreeningResult(
            items=[
                JobTitleScreeningItem(
                    title=job.title,
                    decision="pass",
                    summary="Same family and compatible early-career level.",
                    decision_rationale_type="family_match",
                    source="ai",
                    model_name="groq-test",
                    failure_cause=None,
                    payload={
                        "role_family_alignment": "same_family",
                        "seniority_alignment": "compatible",
                        "modifier_impact": "none",
                        "contradiction_strength": "none",
                    },
                )
            ],
            source="ai",
            model_name="groq-test",
            failure_cause=None,
            payload={},
        ),
    )

    summary = drain_relevance_tasks_now(
        db_session,
        account_id=account.id,
        title_batch_limit=1,
        full_batch_limit=0,
    )
    db_session.refresh(job)
    tasks = db_session.scalars(select(JobRelevanceTask).order_by(JobRelevanceTask.id.asc())).all()
    evaluation_count = db_session.scalar(select(func.count(JobRelevanceEvaluation.id)))

    assert summary == {"title_screening_processed": 1, "full_relevance_processed": 0}
    assert job.relevance_decision == "pending"
    assert job.relevance_source == "pending_full_relevance"
    assert evaluation_count == 0
    assert len(tasks) == 1
    assert tasks[0].phase == "full_relevance"
    assert tasks[0].payload["screening_decision"] == "pass"


def test_drain_relevance_tasks_now_writes_title_screen_rejects(db_session, monkeypatch) -> None:
    account, _profile, _source, job = _create_job_fixture(db_session)
    job.title = "Hardware Engineer"
    job.canonical_key = "acme-hardware-engineer-remote"
    upsert_relevance_task(
        db_session,
        account_id=account.id,
        job_id=job.id,
        phase="title_screening",
        reset_attempts=True,
    )
    db_session.commit()

    monkeypatch.setattr(
        "app.tasks.job_relevance.classify_job_titles",
        lambda *args, **kwargs: JobTitleScreeningResult(
            items=[
                JobTitleScreeningItem(
                    title=job.title,
                    decision="reject",
                    summary="The title is a different role family.",
                    decision_rationale_type="clear_family_mismatch",
                    source="ai",
                    model_name="groq-test",
                    failure_cause=None,
                    payload={
                        "role_family_alignment": "different_family",
                        "seniority_alignment": "uncertain",
                        "modifier_impact": "material_scope_change",
                        "contradiction_strength": "strong",
                    },
                )
            ],
            source="ai",
            model_name="groq-test",
            failure_cause=None,
            payload={},
        ),
    )

    summary = drain_relevance_tasks_now(
        db_session,
        account_id=account.id,
        title_batch_limit=1,
        full_batch_limit=0,
    )
    db_session.refresh(job)
    tasks = db_session.scalars(select(JobRelevanceTask)).all()
    evaluations = db_session.scalars(select(JobRelevanceEvaluation)).all()

    assert summary == {"title_screening_processed": 1, "full_relevance_processed": 0}
    assert job.relevance_decision == "reject"
    assert job.relevance_source == "title_screening"
    assert tasks == []
    assert len(evaluations) == 1
    assert evaluations[0].payload["decision_phase"] == "title_screening"


def test_drain_relevance_tasks_now_keeps_invalid_title_screening_pending(db_session, monkeypatch) -> None:
    account, _profile, _source, job = _create_job_fixture(db_session)
    upsert_relevance_task(
        db_session,
        account_id=account.id,
        job_id=job.id,
        phase="title_screening",
        reset_attempts=True,
    )
    db_session.commit()

    monkeypatch.setattr(
        "app.tasks.job_relevance.classify_job_titles",
        lambda *args, **kwargs: JobTitleScreeningResult(
            items=[
                JobTitleScreeningItem(
                    title=job.title,
                    decision="pass",
                    summary="AI title screening returned an inconsistent result for this title, so it is pending a retry.",
                    decision_rationale_type="ambiguous_but_passed",
                    source="system_fallback",
                    model_name=None,
                    failure_cause="provider_response_invalid",
                    payload={},
                )
            ],
            source="system_fallback",
            model_name=None,
            failure_cause="provider_response_invalid",
            payload={},
        ),
    )

    summary = drain_relevance_tasks_now(
        db_session,
        account_id=account.id,
        title_batch_limit=1,
        full_batch_limit=0,
    )
    db_session.refresh(job)
    task = db_session.scalar(select(JobRelevanceTask).where(JobRelevanceTask.job_id == job.id))
    evaluation_count = db_session.scalar(select(func.count(JobRelevanceEvaluation.id)))

    assert summary == {"title_screening_processed": 1, "full_relevance_processed": 0}
    assert job.relevance_decision == "pending"
    assert job.relevance_source == "pending_title_screening"
    assert evaluation_count == 0
    assert task is not None
    assert task.phase == "title_screening"
    assert task.attempt_count == 1
    assert task.last_failure_cause == "provider_response_invalid"


def test_drain_relevance_tasks_now_reschedules_transient_full_relevance_failures(db_session, monkeypatch) -> None:
    account, _profile, _source, job = _create_job_fixture(db_session)
    job.relevance_source = "pending_full_relevance"
    job.relevance_summary = "Waiting for full AI relevance review."
    upsert_relevance_task(
        db_session,
        account_id=account.id,
        job_id=job.id,
        phase="full_relevance",
        payload={
            "screening_decision": "pass",
            "screening_summary": "Same family and compatible early-career level.",
            "screening_source": "ai",
        },
        reset_attempts=True,
    )
    db_session.commit()

    monkeypatch.setattr(
        "app.tasks.job_relevance.classify_job_relevance_batch",
        lambda *args, **kwargs: [
            JobRelevanceResult(
                decision="review",
                score=None,
                summary="AI relevance classification was rate-limited, so this job needs review.",
                matched_signals=[],
                concerns=["provider_rate_limited"],
                source="system_fallback",
                model_name=None,
                failure_cause="provider_rate_limited",
                payload={"decision_rationale_type": "provider_fallback"},
            )
        ],
    )

    before = datetime.utcnow()
    summary = drain_relevance_tasks_now(
        db_session,
        account_id=account.id,
        title_batch_limit=0,
        full_batch_limit=1,
    )
    db_session.refresh(job)
    task = db_session.scalar(select(JobRelevanceTask).where(JobRelevanceTask.job_id == job.id))
    evaluation_count = db_session.scalar(select(func.count(JobRelevanceEvaluation.id)))

    assert summary == {"title_screening_processed": 0, "full_relevance_processed": 1}
    assert job.relevance_decision == "pending"
    assert job.relevance_source == "pending_full_relevance"
    assert evaluation_count == 0
    assert task is not None
    assert task.phase == "full_relevance"
    assert task.attempt_count == 1
    assert task.last_failure_cause == "provider_rate_limited"
    assert task.available_at >= before
