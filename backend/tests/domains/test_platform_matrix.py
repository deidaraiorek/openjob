from app.domains.applications.platform_matrix import detect_platform_family
from app.domains.jobs.models import ApplyTarget, Job
from app.domains.jobs.target_resolution import refresh_preferred_apply_target


def test_detect_platform_family_classifies_researched_hosts() -> None:
    assert detect_platform_family(destination_url="https://jobs.ashbyhq.com/acme/123") == "ashby"
    assert detect_platform_family(destination_url="https://jobs.smartrecruiters.com/Acme/123") == "smartrecruiters"
    assert detect_platform_family(destination_url="https://wd1.myworkdaysite.com/recruiting/acme/job/123") == "workday"
    assert detect_platform_family(destination_url="https://acme.icims.com/jobs/123/software-engineer/job") == "icims"
    assert detect_platform_family(destination_url="https://jobs.jobvite.com/acme/job/o123") == "jobvite"
    assert detect_platform_family(destination_url="https://example.com/apply/123") == "external"


def test_refresh_preferred_apply_target_prefers_supported_driver_over_future_platform() -> None:
    job = Job(
        canonical_key="acme-software-engineer",
        company_name="Acme",
        title="Software Engineer",
        location="Remote",
    )
    linkedin_target = ApplyTarget(
        id=1,
        target_type="linkedin_easy_apply",
        destination_url="https://www.linkedin.com/jobs/view/123",
        metadata_json={"linkedin_job_id": "123"},
    )
    workday_target = ApplyTarget(
        id=2,
        target_type="external_link",
        destination_url="https://acme.wd1.myworkdaysite.com/recruiting/acme/job/123",
        metadata_json={},
    )
    job.apply_targets = [workday_target, linkedin_target]

    preferred = refresh_preferred_apply_target(job)

    assert preferred is linkedin_target
    assert linkedin_target.is_preferred is True
    assert workday_target.is_preferred is False
