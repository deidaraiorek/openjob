from sqlalchemy import func, select

from app.domains.accounts.service import ensure_account
from app.domains.jobs.deduplication import DiscoveryCandidate, ingest_candidate
from app.domains.jobs.models import ApplyTarget, Job
from app.domains.sources.models import JobSource
from app.tasks.discovery import sync_source


def test_linkedin_discovery_collapses_into_existing_ats_backed_job(db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    greenhouse_source = JobSource(
        account_id=account.id,
        source_key="greenhouse",
        source_type="greenhouse_board",
        name="Greenhouse",
        base_url="https://boards.greenhouse.io/acme",
        settings_json={"board_token": "acme"},
    )
    linkedin_source = JobSource(
        account_id=account.id,
        source_key="linkedin",
        source_type="linkedin_search",
        name="LinkedIn",
        base_url="https://www.linkedin.com/jobs/search",
        settings_json={"keywords": ["new grad", "software engineer i"]},
    )
    db_session.add_all([greenhouse_source, linkedin_source])
    db_session.commit()
    db_session.refresh(greenhouse_source)
    db_session.refresh(linkedin_source)

    greenhouse_candidate = DiscoveryCandidate(
        source_type="greenhouse_board",
        company_name="Acme",
        title="Software Engineer I",
        location="Remote",
        listing_url="https://boards.greenhouse.io/acme/jobs/123",
        apply_url="https://boards.greenhouse.io/acme/jobs/123",
        apply_target_type="greenhouse_apply",
        external_job_id="123",
        metadata={"board_token": "acme", "job_post_id": "123"},
    )
    ingest_candidate(db_session, account, greenhouse_source, greenhouse_candidate)
    db_session.commit()

    linkedin_payload = {
        "jobs": [
            {
                "job_posting_id": "ln-123",
                "title": "Software Engineer I",
                "company_name": "Acme",
                "location": "Remote",
                "job_url": "https://www.linkedin.com/jobs/view/ln-123",
                "apply_url": "https://www.linkedin.com/jobs/view/ln-123",
                "easy_apply": True,
            }
        ]
    }

    summary = sync_source(db_session, linkedin_source.id, raw_payload=linkedin_payload)

    job_count = db_session.scalar(select(func.count(Job.id)))
    targets = db_session.scalars(select(ApplyTarget).order_by(ApplyTarget.id)).all()

    assert summary == {"processed": 1, "created": 0, "updated": 1}
    assert job_count == 1
    assert len(targets) == 2
    preferred_target = next(target for target in targets if target.is_preferred)
    assert preferred_target.target_type == "greenhouse_apply"
