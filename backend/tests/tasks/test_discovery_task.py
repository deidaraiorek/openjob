from sqlalchemy import func, select

from app.domains.accounts.service import ensure_account
from app.domains.jobs.models import ApplyTarget, Job, JobSighting
from app.domains.role_profiles.models import RoleProfile
from app.domains.sources.models import JobSource
from app.tasks.discovery import sync_source


def test_sync_source_ingests_greenhouse_jobs_and_queues_pass_titles(db_session, monkeypatch) -> None:
    queued: dict[str, object] = {}
    monkeypatch.setattr(
        "app.tasks.discovery.screen_candidate_titles",
        lambda profile, candidates: {
            candidate.title: type(
                "ScreenedTitle",
                (),
                {
                    "title": candidate.title,
                    "decision": "pass",
                    "summary": "Relevant title.",
                    "source": "ai",
                    "model_name": "groq-test",
                    "failure_cause": None,
                    "payload": {},
                },
            )()
            for candidate in candidates
        },
    )
    monkeypatch.setattr(
        "app.tasks.discovery.evaluate_job_batch_now",
        lambda session, account_id, job_ids: queued.update({"account_id": account_id, "job_ids": list(job_ids)}) or len(job_ids),
    )

    account = ensure_account(db_session, "owner@example.com")
    source = JobSource(
        account_id=account.id,
        source_key="greenhouse",
        source_type="greenhouse_board",
        name="Greenhouse",
        base_url="https://boards.greenhouse.io/acme",
        settings_json={"board_token": "acme"},
    )
    profile = RoleProfile(
        account_id=account.id,
        prompt="new grad backend software engineer",
        generated_titles=[],
        generated_keywords=[],
    )
    db_session.add_all([source, profile])
    db_session.commit()
    db_session.refresh(source)

    payload = {
        "company_name": "Acme",
        "jobs": [
            {
                "id": 123,
                "title": "Software Engineer I",
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/123",
                "location": {"name": "Remote"},
            }
        ],
    }

    summary = sync_source(db_session, source.id, raw_payload=payload)

    job_count = db_session.scalar(select(func.count(Job.id)))
    sighting_count = db_session.scalar(select(func.count(JobSighting.id)))
    target_count = db_session.scalar(select(func.count(ApplyTarget.id)))
    db_session.refresh(profile)

    assert summary == {"processed": 1, "created": 1, "updated": 0}
    assert job_count == 1
    assert sighting_count == 1
    assert target_count == 1
    assert profile.generated_titles == []
    assert profile.generated_keywords == []
    target = db_session.scalar(select(ApplyTarget))
    job = db_session.scalar(select(Job))
    assert job is not None
    assert target is not None
    assert job.relevance_decision == "review"
    assert job.relevance_source == "relevance_queue"
    assert "queued for deeper ai relevance review" in (job.relevance_summary or "").lower()
    assert target.metadata_json["board_token"] == "acme"
    assert target.metadata_json["job_post_id"] == "123"
    assert queued == {"account_id": account.id, "job_ids": [job.id]}


def test_sync_source_treats_non_reject_title_screen_results_as_phase_two_candidates(db_session, monkeypatch) -> None:
    queued_job_ids: list[int] = []
    account = ensure_account(db_session, "owner@example.com")
    source = JobSource(
        account_id=account.id,
        source_key="simplify",
        source_type="github_curated",
        name="Simplify",
        base_url="https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/README.md",
        settings_json={},
    )
    profile = RoleProfile(
        account_id=account.id,
        prompt="software engineer 1 and new grad software roles",
        generated_titles=["Software Engineer I", "New Grad Software Engineer"],
        generated_keywords=["new grad software engineer", "software engineer entry level"],
    )
    db_session.add_all([source, profile])
    db_session.commit()
    db_session.refresh(source)

    monkeypatch.setattr(
        "app.tasks.discovery.screen_candidate_titles",
        lambda profile, candidates: {
            candidate.title: type(
                "ScreenedTitle",
                (),
                {
                    "title": candidate.title,
                    "decision": (
                        "pass"
                        if candidate.title == "Software Engineer 1"
                        else "review"
                    ),
                    "summary": (
                        "Looks like a relevant software role."
                        if candidate.title == "Software Engineer 1"
                        else "Title is ambiguous and should stay in review."
                    ),
                    "source": "ai",
                    "model_name": "groq-test",
                    "failure_cause": None,
                    "payload": {},
                },
            )()
            for candidate in candidates
        },
    )
    monkeypatch.setattr(
        "app.tasks.discovery.evaluate_job_batch_now",
        lambda session, account_id, job_ids: queued_job_ids.extend(job_ids) or len(job_ids),
    )

    markdown = """
<table>
<tbody>
<tr>
<td><strong><a href="https://simplify.jobs/c/Acme">Acme</a></strong></td>
<td>Software Engineer 1</td>
<td>Remote</td>
<td><a href="https://boards.greenhouse.io/acme/jobs/123">Apply</a></td>
</tr>
<tr>
<td><strong><a href="https://simplify.jobs/c/RoboticsCo">RoboticsCo</a></strong></td>
<td>Hardware Engineer</td>
<td>San Jose, CA</td>
<td><a href="https://example.com/jobs/456">Apply</a></td>
</tr>
</tbody>
</table>
"""

    summary = sync_source(db_session, source.id, raw_payload=markdown)

    jobs = db_session.scalars(select(Job).order_by(Job.id.asc())).all()
    assert summary == {"processed": 2, "created": 2, "updated": 0}
    assert [job.title for job in jobs] == ["Software Engineer 1", "Hardware Engineer"]
    assert jobs[0].relevance_source == "relevance_queue"
    assert jobs[1].relevance_source == "relevance_queue"
    assert queued_job_ids == [jobs[0].id, jobs[1].id]


def test_sync_source_does_not_queue_title_screen_rejects(db_session, monkeypatch) -> None:
    queued_job_ids: list[int] = []
    account = ensure_account(db_session, "owner@example.com")
    source = JobSource(
        account_id=account.id,
        source_key="ping",
        source_type="greenhouse_board",
        name="Ping",
        base_url="https://job-boards.greenhouse.io/pingidentity",
        settings_json={"board_token": "pingidentity"},
    )
    profile = RoleProfile(
        account_id=account.id,
        prompt="software engineer 1 / new grad positions",
        generated_titles=["Software Engineer I", "New Grad Software Engineer"],
        generated_keywords=["new grad software engineer", "software engineer entry level"],
    )
    db_session.add_all([source, profile])
    db_session.commit()
    db_session.refresh(source)

    monkeypatch.setattr(
        "app.tasks.discovery.screen_candidate_titles",
        lambda profile, candidates: {
            candidate.title: type(
                "ScreenedTitle",
                (),
                {
                    "title": candidate.title,
                    "decision": "pass" if candidate.title == "Software Engineer I" else "reject",
                    "summary": "Screened.",
                    "source": "ai",
                    "model_name": "groq-test",
                    "failure_cause": None,
                    "payload": {},
                },
            )()
            for candidate in candidates
        },
    )
    monkeypatch.setattr(
        "app.tasks.discovery.evaluate_job_batch_now",
        lambda session, account_id, job_ids: queued_job_ids.extend(job_ids) or len(job_ids),
    )

    payload = {
        "company_name": "Ping Identity",
        "jobs": [
            {
                "id": 401,
                "title": "Site Reliability Engineer II - Government Cloud",
                "absolute_url": "https://job-boards.greenhouse.io/pingidentity/jobs/401",
                "location": {"name": "USA - Remote"},
            },
            {
                "id": 402,
                "title": "Software Engineer I",
                "absolute_url": "https://job-boards.greenhouse.io/pingidentity/jobs/402",
                "location": {"name": "USA - Remote"},
            },
        ],
    }

    summary = sync_source(db_session, source.id, raw_payload=payload)
    jobs = db_session.scalars(select(Job).order_by(Job.id.asc())).all()

    assert summary == {"processed": 2, "created": 2, "updated": 0}
    assert [job.title for job in jobs] == [
        "Site Reliability Engineer II - Government Cloud",
        "Software Engineer I",
    ]
    assert jobs[0].relevance_decision == "reject"
    assert jobs[0].relevance_source == "title_screening"
    assert jobs[1].relevance_source == "relevance_queue"
    assert queued_job_ids == [jobs[1].id]


def test_sync_source_derives_greenhouse_board_token_from_base_url(db_session, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.tasks.discovery.screen_candidate_titles",
        lambda profile, candidates: {
            candidate.title: type(
                "ScreenedTitle",
                (),
                {
                    "title": candidate.title,
                    "decision": "pass",
                    "summary": "Relevant title.",
                    "source": "ai",
                    "model_name": "groq-test",
                    "failure_cause": None,
                    "payload": {},
                },
            )()
            for candidate in candidates
        },
    )
    monkeypatch.setattr(
        "app.tasks.discovery.evaluate_job_batch_now",
        lambda session, account_id, job_ids: len(job_ids),
    )

    account = ensure_account(db_session, "owner@example.com")
    source = JobSource(
        account_id=account.id,
        source_key="alt",
        source_type="greenhouse_board",
        name="alt",
        base_url="https://job-boards.greenhouse.io/alt",
        settings_json={},
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)

    payload = {
        "company_name": "Alt",
        "jobs": [
            {
                "id": 501,
                "title": "Software Engineer I",
                "absolute_url": "https://job-boards.greenhouse.io/alt/jobs/501",
                "location": {"name": "Remote"},
            }
        ],
    }

    summary = sync_source(db_session, source.id, raw_payload=payload)
    target = db_session.scalar(select(ApplyTarget))

    assert summary == {"processed": 1, "created": 1, "updated": 0}
    assert target is not None
    assert target.metadata_json["board_token"] == "alt"


def test_sync_source_queues_all_pass_titles_for_phase_two(db_session, monkeypatch) -> None:
    queued_job_ids: list[int] = []

    monkeypatch.setattr(
        "app.tasks.discovery.screen_candidate_titles",
        lambda profile, candidates: {
            candidate.title: type(
                "ScreenedTitle",
                (),
                {
                    "title": candidate.title,
                    "decision": "pass",
                    "summary": "Relevant title.",
                    "source": "ai",
                    "model_name": "groq-test",
                    "failure_cause": None,
                    "payload": {},
                },
            )()
            for candidate in candidates
        },
    )
    monkeypatch.setattr(
        "app.tasks.discovery.evaluate_job_batch_now",
        lambda session, account_id, job_ids: queued_job_ids.extend(job_ids) or len(job_ids),
    )

    account = ensure_account(db_session, "owner@example.com")
    source = JobSource(
        account_id=account.id,
        source_key="cap-test",
        source_type="greenhouse_board",
        name="Cap Test",
        base_url="https://boards.greenhouse.io/cap",
        settings_json={"board_token": "cap"},
    )
    profile = RoleProfile(
        account_id=account.id,
        prompt="software engineer new grad",
        generated_titles=[],
        generated_keywords=[],
    )
    db_session.add_all([source, profile])
    db_session.commit()
    db_session.refresh(source)

    payload = {
        "company_name": "Cap Co",
        "jobs": [
            {
                "id": 1,
                "title": "Software Engineer I",
                "absolute_url": "https://boards.greenhouse.io/cap/jobs/1",
                "location": {"name": "Remote"},
            },
            {
                "id": 2,
                "title": "New Grad Software Engineer",
                "absolute_url": "https://boards.greenhouse.io/cap/jobs/2",
                "location": {"name": "Remote"},
            },
        ],
    }

    sync_source(db_session, source.id, raw_payload=payload)
    jobs = db_session.scalars(select(Job).order_by(Job.id.asc())).all()

    assert len(queued_job_ids) == 2
    assert jobs[0].relevance_source == "relevance_queue"
    assert jobs[1].relevance_source == "relevance_queue"
    assert "queued for deeper ai relevance review" in (jobs[0].relevance_summary or "").lower()
    assert "queued for deeper ai relevance review" in (jobs[1].relevance_summary or "").lower()
