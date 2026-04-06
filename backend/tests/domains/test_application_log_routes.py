from sqlalchemy import func, select

from app.domains.accounts.service import ensure_account
from app.domains.applications.models import ApplicationEvent, ApplicationRun
from app.domains.jobs.models import ApplyTarget, Job, JobRelevanceEvaluation, JobSighting
from app.domains.questions.models import QuestionTask
from app.domains.sources.models import JobSource


def test_job_detail_returns_sightings_targets_questions_and_application_history(
    auth_client,
    db_session,
) -> None:
    account = ensure_account(db_session, "owner@example.com")

    source = JobSource(
        account_id=account.id,
        source_key="greenhouse-main",
        source_type="greenhouse_board",
        name="Greenhouse Main",
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
    )
    db_session.add_all([source, job])
    db_session.commit()
    db_session.refresh(source)
    db_session.refresh(job)

    sighting_one = JobSighting(
        job_id=job.id,
        source_id=source.id,
        external_job_id="gh-123",
        listing_url="https://github.com/SimplifyJobs/example",
        apply_url="https://boards.greenhouse.io/acme/jobs/123",
        raw_payload={"source": "github"},
    )
    sighting_two = JobSighting(
        job_id=job.id,
        source_id=source.id,
        external_job_id="gh-123-direct",
        listing_url="https://boards.greenhouse.io/acme/jobs/123",
        apply_url="https://boards.greenhouse.io/acme/jobs/123",
        raw_payload={"source": "greenhouse"},
    )
    apply_target = ApplyTarget(
        job_id=job.id,
        target_type="greenhouse_apply",
        destination_url="https://boards.greenhouse.io/acme/jobs/123/apply",
        is_preferred=True,
        metadata_json={"source": "greenhouse"},
    )
    relevance_evaluation = JobRelevanceEvaluation(
        account_id=account.id,
        job_id=job.id,
        decision="match",
        source="ai",
        score=0.92,
        summary="Strong early-career software match.",
        matched_signals=["software engineer i", "remote"],
        concerns=[],
        model_name="groq-test",
        payload={},
    )
    question_task = QuestionTask(
        account_id=account.id,
        job_id=job.id,
        question_fingerprint="linkedin-profile",
        prompt_text="LinkedIn profile URL",
        field_type="text",
        option_labels=[],
        status="new",
    )
    db_session.add_all([sighting_one, sighting_two, apply_target, relevance_evaluation, question_task])
    db_session.commit()
    db_session.refresh(apply_target)

    run = ApplicationRun(
        account_id=account.id,
        job_id=job.id,
        apply_target_id=apply_target.id,
        status="blocked_missing_answer",
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    event = ApplicationEvent(
        application_run_id=run.id,
        event_type="blocked_missing_answer",
        payload={"question_fingerprint": "linkedin-profile"},
    )
    db_session.add(event)
    db_session.commit()

    job_count = db_session.scalar(select(func.count(Job.id)))
    sighting_count = db_session.scalar(select(func.count(JobSighting.id)))

    assert job_count == 1
    assert sighting_count == 2

    response = auth_client.get(f"/api/jobs/{job.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["canonical_key"] == "acme-software-engineer-i-remote"
    assert len(body["sightings"]) == 2
    assert body["preferred_apply_target"]["target_type"] == "greenhouse_apply"
    assert body["relevance_decision"] == "match"
    assert body["relevance_summary"] == "Strong early-career software match."
    assert body["relevance_evaluations"][0]["model_name"] == "groq-test"
    assert body["question_tasks"][0]["prompt_text"] == "LinkedIn profile URL"
    assert body["application_runs"][0]["status"] == "blocked_missing_answer"
    assert body["application_runs"][0]["events"][0]["event_type"] == "blocked_missing_answer"
