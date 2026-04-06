from sqlalchemy import func, select

from app.domains.accounts.service import ensure_account
from app.domains.jobs.deduplication import DiscoveryCandidate, ingest_candidate
from app.domains.jobs.models import ApplyTarget, Job, JobSighting
from app.domains.sources.models import JobSource


def test_cross_source_duplicates_collapse_to_one_job_and_prefer_direct_ats(db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    github_source = JobSource(
        account_id=account.id,
        source_key="github",
        source_type="github_curated",
        name="GitHub",
        base_url="https://raw.githubusercontent.com/SimplifyJobs/example.md",
        settings_json={},
    )
    greenhouse_source = JobSource(
        account_id=account.id,
        source_key="greenhouse",
        source_type="greenhouse_board",
        name="Greenhouse",
        base_url="https://boards.greenhouse.io/acme",
        settings_json={"board_token": "acme"},
    )
    db_session.add_all([github_source, greenhouse_source])
    db_session.commit()
    db_session.refresh(github_source)
    db_session.refresh(greenhouse_source)

    github_candidate = DiscoveryCandidate(
        source_type="github_curated",
        company_name="Acme",
        title="Software Engineer I",
        location="Remote",
        listing_url="https://simplify.jobs/jobs/acme-se1",
        apply_url="https://boards.greenhouse.io/acme/jobs/123",
        apply_target_type="external_link",
        external_job_id="github-acme-se1",
    )
    greenhouse_candidate = DiscoveryCandidate(
        source_type="greenhouse_board",
        company_name="Acme",
        title="Software Engineer I",
        location="Remote",
        listing_url="https://boards.greenhouse.io/acme/jobs/123",
        apply_url="https://boards.greenhouse.io/acme/jobs/123",
        apply_target_type="greenhouse_apply",
        external_job_id="123",
    )

    ingest_candidate(db_session, account, github_source, github_candidate)
    ingest_candidate(db_session, account, greenhouse_source, greenhouse_candidate)
    db_session.commit()

    job_count = db_session.scalar(select(func.count(Job.id)))
    sighting_count = db_session.scalar(select(func.count(JobSighting.id)))
    targets = db_session.scalars(select(ApplyTarget).order_by(ApplyTarget.id)).all()

    assert job_count == 1
    assert sighting_count == 2
    assert len(targets) == 2
    preferred_target = next(target for target in targets if target.is_preferred)
    assert preferred_target.target_type == "greenhouse_apply"
