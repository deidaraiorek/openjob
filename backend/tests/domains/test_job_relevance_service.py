from app.domains.accounts.service import ensure_account
from app.domains.jobs.deduplication import DiscoveryCandidate
from app.domains.jobs.models import Job
from app.domains.jobs.relevance import (
    apply_relevance_result,
    cached_relevance_for_job,
    evaluate_candidate_relevance,
)
from app.domains.role_profiles.models import RoleProfile
from app.integrations.openai.job_relevance import JobRelevanceResult


def test_evaluate_candidate_relevance_uses_structured_ai_result(monkeypatch, db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    profile = RoleProfile(
        account_id=account.id,
        prompt="new grad backend software engineer",
        generated_titles=["Software Engineer I"],
        generated_keywords=["new grad", "backend"],
    )

    captured: dict[str, object] = {}

    def fake_classify(profile, **kwargs):
        captured.update(kwargs)
        return JobRelevanceResult(
            decision="match",
            score=0.96,
            summary="Strong early-career backend match.",
            matched_signals=["software engineer i"],
            concerns=[],
            source="ai",
            model_name="groq-test",
            failure_cause=None,
            payload={"decision": "match"},
        )

    monkeypatch.setattr("app.domains.jobs.relevance.classify_job_relevance", fake_classify)

    result = evaluate_candidate_relevance(
        profile,
        DiscoveryCandidate(
            source_type="greenhouse_board",
            company_name="Acme",
            title="Software Engineer I",
            listing_url="https://boards.greenhouse.io/acme/jobs/1",
            location="Remote",
            apply_url="https://boards.greenhouse.io/acme/jobs/1",
            apply_target_type="greenhouse_apply",
        ),
    )

    assert result.decision == "match"
    assert result.score == 0.96
    assert result.summary == "Strong early-career backend match."
    assert captured["matched_titles"] == ["Software Engineer I"]


def test_evaluate_candidate_relevance_rejects_before_ai_when_title_misses_catalog(monkeypatch, db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    profile = RoleProfile(
        account_id=account.id,
        prompt="software engineer 1 / new grad",
        generated_titles=["Software Engineer I", "New Grad Software Engineer"],
        generated_keywords=[],
    )

    called = {"value": False}

    def fake_classify(profile, **kwargs):
        called["value"] = True
        raise AssertionError("AI should not be called when title gate fails")

    monkeypatch.setattr("app.domains.jobs.relevance.classify_job_relevance", fake_classify)

    result = evaluate_candidate_relevance(
        profile,
        DiscoveryCandidate(
            source_type="greenhouse_board",
            company_name="Acme",
            title="Data Engineer",
            listing_url="https://boards.greenhouse.io/acme/jobs/2",
            location="Remote",
            apply_url="https://boards.greenhouse.io/acme/jobs/2",
            apply_target_type="greenhouse_apply",
        ),
    )

    assert called["value"] is False
    assert result.decision == "reject"
    assert result.source == "title_gate"


def test_apply_relevance_result_updates_job_and_writes_history(db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    profile = RoleProfile(
        account_id=account.id,
        prompt="new grad software engineer",
        generated_titles=["Software Engineer I"],
        generated_keywords=["new grad"],
    )
    job = Job(
        account_id=account.id,
        canonical_key="acme-role",
        company_name="Acme",
        title="Software Engineer I",
        location="Remote",
        status="discovered",
    )
    db_session.add_all([profile, job])
    db_session.commit()
    db_session.refresh(job)

    evaluation = apply_relevance_result(
        db_session,
        account_id=account.id,
        job=job,
        result=JobRelevanceResult(
            decision="review",
            score=0.5,
            summary="Looks close, but title is broad enough to review.",
            matched_signals=["software"],
            concerns=["broad title"],
            source="ai",
            model_name="groq-test",
            failure_cause=None,
            payload={"decision": "review"},
        ),
        profile=profile,
    )
    db_session.commit()
    db_session.refresh(job)

    assert job.relevance_decision == "review"
    assert job.relevance_summary == "Looks close, but title is broad enough to review."
    assert evaluation.profile_snapshot_hash is not None


def test_cached_relevance_skips_provider_failure_evaluations(db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    profile = RoleProfile(
        account_id=account.id,
        prompt="new grad software engineer",
        generated_titles=["Software Engineer I"],
        generated_keywords=["new grad"],
    )
    job = Job(
        account_id=account.id,
        canonical_key="acme-role",
        company_name="Acme",
        title="Software Engineer I",
        location="Remote",
        status="discovered",
    )
    db_session.add_all([profile, job])
    db_session.commit()
    db_session.refresh(job)

    apply_relevance_result(
        db_session,
        account_id=account.id,
        job=job,
        result=JobRelevanceResult(
            decision="review",
            score=None,
            summary="AI relevance classification was rate-limited, so this job needs review.",
            matched_signals=[],
            concerns=["provider_rate_limited"],
            source="system_fallback",
            model_name=None,
            failure_cause="provider_rate_limited",
            payload={},
        ),
        profile=profile,
    )
    db_session.commit()
    db_session.refresh(job)

    cached = cached_relevance_for_job(
        profile,
        job,
        source_type="greenhouse_board",
        apply_target_type="greenhouse_apply",
        description_snippet=None,
    )

    assert cached is None
