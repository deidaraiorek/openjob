from app.domains.accounts.service import ensure_account
from app.domains.jobs.models import Job


def test_job_list_filters_by_relevance(auth_client, db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    db_session.add_all(
        [
            Job(
                account_id=account.id,
                canonical_key="match-job",
                company_name="Acme",
                title="Software Engineer I",
                location="Remote",
                status="discovered",
                relevance_decision="match",
                relevance_source="ai",
                relevance_summary="Good match.",
            ),
            Job(
                account_id=account.id,
                canonical_key="review-job",
                company_name="AmbiguousCo",
                title="Engineer",
                location="Remote",
                status="discovered",
                relevance_decision="review",
                relevance_source="system_fallback",
                relevance_summary="Needs review.",
            ),
            Job(
                account_id=account.id,
                canonical_key="reject-job",
                company_name="HardwareCo",
                title="Hardware Engineer",
                location="Onsite",
                status="discovered",
                relevance_decision="reject",
                relevance_source="ai",
                relevance_summary="Out of scope.",
            ),
        ]
    )
    db_session.commit()

    review_response = auth_client.get("/api/jobs?relevance=review")
    reject_response = auth_client.get("/api/jobs?relevance=reject")
    active_response = auth_client.get("/api/jobs")

    assert [job["title"] for job in review_response.json()] == ["Engineer"]
    assert [job["title"] for job in reject_response.json()] == ["Hardware Engineer"]
    assert [job["title"] for job in active_response.json()] == ["Engineer", "Software Engineer I"]


def test_manual_job_relevance_override_updates_effective_decision(auth_client, db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    job = Job(
        account_id=account.id,
        canonical_key="manual-job",
        company_name="Acme",
        title="Software Engineer I",
        location="Remote",
        status="discovered",
        relevance_decision="review",
        relevance_source="ai",
        relevance_summary="Needs review.",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    response = auth_client.patch(
        f"/api/jobs/{job.id}/relevance",
        json={"decision": "reject"},
    )

    assert response.status_code == 200
    assert response.json()["relevance_decision"] == "reject"
    assert response.json()["relevance_source"] == "manual_exclude"
