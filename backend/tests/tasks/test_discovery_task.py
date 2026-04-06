from sqlalchemy import func, select

from app.domains.accounts.service import ensure_account
from app.domains.jobs.models import ApplyTarget, Job, JobSighting
from app.domains.role_profiles.models import RoleProfile
from app.domains.sources.models import JobSource
from app.tasks.discovery import sync_source


def test_sync_source_ingests_greenhouse_jobs_and_expands_role_profile(db_session, monkeypatch) -> None:
    from app.integrations.openai.job_relevance import JobRelevanceResult

    monkeypatch.setattr(
        "app.tasks.discovery.expand_role_profile_prompt",
        lambda prompt: {
            "generated_titles": ["Software Engineer I", "Backend Engineer"],
            "generated_keywords": [],
        },
    )
    monkeypatch.setattr(
        "app.tasks.discovery.evaluate_candidate_relevance",
        lambda profile, candidate: JobRelevanceResult(
            decision="match",
            score=0.95,
            summary="Strong match.",
            matched_signals=["software engineer i"],
            concerns=[],
            source="ai",
            model_name="groq-test",
            failure_cause=None,
            payload={},
        ),
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
    assert "Software Engineer I" in profile.generated_titles
    assert profile.generated_keywords == []
    target = db_session.scalar(select(ApplyTarget))
    assert target is not None
    assert target.metadata_json["board_token"] == "acme"
    assert target.metadata_json["job_post_id"] == "123"


def test_sync_source_filters_irrelevant_titles_from_software_profile(db_session, monkeypatch) -> None:
    from app.integrations.openai.job_relevance import JobRelevanceResult

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

    def fake_result(profile, candidate):
        if candidate.title == "Software Engineer 1":
            return JobRelevanceResult(
                decision="match",
                score=0.94,
                summary="Relevant early-career software role.",
                matched_signals=["software engineer 1"],
                concerns=[],
                source="ai",
                model_name="groq-test",
                failure_cause=None,
                payload={},
            )
        return JobRelevanceResult(
            decision="reject",
            score=0.03,
            summary="Hardware role is outside the role profile.",
            matched_signals=[],
            concerns=["hardware"],
            source="ai",
            model_name="groq-test",
            failure_cause=None,
            payload={},
        )

    monkeypatch.setattr("app.tasks.discovery.evaluate_candidate_relevance", fake_result)

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
    assert summary == {"processed": 2, "created": 1, "updated": 0}
    assert [job.title for job in jobs] == ["Software Engineer 1"]
    assert [job.relevance_decision for job in jobs] == ["match"]


def test_sync_source_does_not_treat_engineer_two_as_engineer_one(db_session, monkeypatch) -> None:
    from app.integrations.openai.job_relevance import JobRelevanceResult

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

    def fake_result(profile, candidate):
        if candidate.title == "Software Engineer I":
            return JobRelevanceResult(
                decision="match",
                score=0.97,
                summary="Exact early-career software match.",
                matched_signals=["software engineer i"],
                concerns=[],
                source="ai",
                model_name="groq-test",
                failure_cause=None,
                payload={},
            )
        return JobRelevanceResult(
            decision="reject",
            score=0.08,
            summary="Not an entry-level software engineer role.",
            matched_signals=[],
            concerns=["seniority mismatch", "site reliability focus"],
            source="ai",
            model_name="groq-test",
            failure_cause=None,
            payload={},
        )

    monkeypatch.setattr("app.tasks.discovery.evaluate_candidate_relevance", fake_result)

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

    assert summary == {"processed": 2, "created": 1, "updated": 0}
    assert [job.title for job in jobs] == ["Software Engineer I"]
    assert [job.relevance_decision for job in jobs] == ["match"]


def test_sync_source_derives_greenhouse_board_token_from_base_url(db_session, monkeypatch) -> None:
    from app.integrations.openai.job_relevance import JobRelevanceResult

    monkeypatch.setattr(
        "app.tasks.discovery.evaluate_candidate_relevance",
        lambda profile, candidate: JobRelevanceResult(
            decision="match",
            score=0.9,
            summary="Relevant role.",
            matched_signals=["software engineer"],
            concerns=[],
            source="ai",
            model_name="groq-test",
            failure_cause=None,
            payload={},
        ),
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
