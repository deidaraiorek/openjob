from __future__ import annotations

from sqlalchemy import select

from app.domains.accounts.service import ensure_account
from app.domains.jobs.models import ApplyTarget, Job, JobRelevanceEvaluation, JobSighting
from app.domains.role_profiles.models import RoleProfile
from app.domains.sources.models import JobSource
from app.integrations.openai.job_relevance import JobRelevanceResult
from app.tasks.job_relevance import evaluate_job_batch_now


def test_evaluate_job_batch_now_applies_batched_relevance_results(db_session, monkeypatch) -> None:
    account = ensure_account(db_session, "owner@example.com")
    profile = RoleProfile(
        account_id=account.id,
        prompt="new grad backend software engineer",
        generated_titles=[],
        generated_keywords=[],
    )
    source = JobSource(
        account_id=account.id,
        source_key="greenhouse",
        source_type="greenhouse_board",
        name="Greenhouse",
        base_url="https://boards.greenhouse.io/acme",
        settings_json={},
    )
    job = Job(
        account_id=account.id,
        canonical_key="acme-software-engineer-i-remote",
        company_name="Acme",
        title="Software Engineer I",
        location="Remote",
        status="discovered",
        relevance_decision="review",
        relevance_source="relevance_queue",
        relevance_summary="Title passed screening and is queued for deeper AI relevance review.",
    )
    sighting = JobSighting(
        job=job,
        source=source,
        external_job_id="123",
        listing_url="https://boards.greenhouse.io/acme/jobs/123",
        apply_url="https://boards.greenhouse.io/acme/jobs/123",
        raw_payload={},
    )
    target = ApplyTarget(
        job=job,
        target_type="greenhouse_apply",
        destination_url="https://boards.greenhouse.io/acme/jobs/123",
        is_preferred=True,
        metadata_json={},
    )
    queued_evaluation = JobRelevanceEvaluation(
        account_id=account.id,
        job=job,
        decision="review",
        source="relevance_queue",
        score=None,
        summary="Title passed screening and is queued for deeper AI relevance review.",
        matched_signals=["Software Engineer I"],
        concerns=["queued_relevance"],
        model_name="groq-test",
        profile_snapshot_hash=None,
        payload={
            "screening_decision": "pass",
            "screening_summary": "Relevant title.",
            "screening_source": "ai",
            "failure_cause": "queued_for_async_relevance",
        },
    )
    db_session.add_all([profile, source, job, sighting, target, queued_evaluation])
    db_session.commit()

    def fake_batch(profile, jobs, settings=None, client=None):
        assert len(jobs) == 1
        assert jobs[0].title_screening_decision == "pass"
        return [
            JobRelevanceResult(
                decision="match",
                score=0.97,
                summary="Strong backend new-grad fit.",
                matched_signals=["software engineer i"],
                concerns=[],
                source="ai",
                model_name="groq-test",
                failure_cause=None,
                payload={"decision": "match"},
            )
        ]

    monkeypatch.setattr("app.tasks.job_relevance.classify_job_relevance_batch", fake_batch)

    processed = evaluate_job_batch_now(session=db_session, account_id=account.id, job_ids=[job.id])
    refreshed_job = db_session.scalar(select(Job).where(Job.id == job.id))

    assert processed == 1
    assert refreshed_job is not None
    assert refreshed_job.relevance_decision == "match"
    assert refreshed_job.relevance_source == "ai"
    assert refreshed_job.relevance_summary == "Strong backend new-grad fit."
