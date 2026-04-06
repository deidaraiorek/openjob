from sqlalchemy import func, select

from app.domains.accounts.service import ensure_account
from app.domains.jobs.models import Job, JobRelevanceEvaluation


def test_job_can_store_lifecycle_and_relevance_independently(db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    job = Job(
        account_id=account.id,
        canonical_key="acme-software-engineer-i",
        company_name="Acme",
        title="Software Engineer I",
        location="Remote",
        status="blocked_missing_answer",
        relevance_decision="match",
        relevance_source="ai",
        relevance_score=0.93,
        relevance_summary="Aligned with new-grad software intent.",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    assert job.status == "blocked_missing_answer"
    assert job.relevance_decision == "match"
    assert job.relevance_source == "ai"
    assert job.relevance_score == 0.93


def test_job_relevance_evaluations_are_append_only_history(db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    job = Job(
        account_id=account.id,
        canonical_key="hardware-role",
        company_name="HardwareCo",
        title="Hardware Engineer",
        location="San Jose, CA",
        status="discovered",
        relevance_decision="review",
        relevance_source="ai",
        relevance_summary="Needs review.",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    db_session.add_all(
        [
            JobRelevanceEvaluation(
                account_id=account.id,
                job_id=job.id,
                decision="review",
                source="ai",
                score=0.41,
                summary="Title looks adjacent to software but unclear.",
                matched_signals=["engineer"],
                concerns=["discipline unclear"],
                payload={},
            ),
            JobRelevanceEvaluation(
                account_id=account.id,
                job_id=job.id,
                decision="reject",
                source="manual_exclude",
                score=None,
                summary="User marked this role as out of scope.",
                matched_signals=[],
                concerns=["manual override"],
                payload={},
            ),
        ]
    )
    db_session.commit()

    evaluation_count = db_session.scalar(
        select(func.count(JobRelevanceEvaluation.id)).where(JobRelevanceEvaluation.job_id == job.id)
    )

    assert evaluation_count == 2
