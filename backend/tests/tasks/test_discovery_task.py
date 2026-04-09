from sqlalchemy import func, select

from app.domains.accounts.service import ensure_account
from app.domains.jobs.models import ApplyTarget, Job, JobRelevanceEvaluation, JobRelevanceTask, JobSighting
from app.domains.role_profiles.models import RoleProfile
from app.domains.sources.models import JobSource
from app.integrations.openai.job_title_screening import JobTitleScreeningItem, JobTitleScreeningResult
from app.tasks.discovery import sync_source


def test_sync_source_ingests_greenhouse_jobs_and_creates_title_screening_tasks(db_session, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.tasks.discovery.drain_relevance_tasks_now",
        lambda session, account_id, title_batch_limit, full_batch_limit: {
            "title_screening_processed": 0,
            "full_relevance_processed": 0,
        },
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

    job = db_session.scalar(select(Job))
    task = db_session.scalar(select(JobRelevanceTask))
    target = db_session.scalar(select(ApplyTarget))
    evaluation_count = db_session.scalar(select(func.count(JobRelevanceEvaluation.id)))

    assert summary == {
        "processed": 1,
        "created": 1,
        "updated": 0,
        "pending_title_screening": 1,
        "pending_full_relevance": 0,
    }
    assert job is not None
    assert job.relevance_decision == "pending"
    assert job.relevance_source == "pending_title_screening"
    assert task is not None
    assert task.phase == "title_screening"
    assert evaluation_count == 0
    assert target is not None
    assert target.metadata_json["board_token"] == "acme"
    assert target.metadata_json["job_post_id"] == "123"


def test_sync_source_inline_title_screening_enqueues_full_relevance_for_pass(db_session, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.tasks.job_relevance.classify_job_titles",
        lambda *args, **kwargs: JobTitleScreeningResult(
            items=[
                JobTitleScreeningItem(
                    title="Software Engineer I",
                    decision="pass",
                    summary="Same family and compatible level.",
                    decision_rationale_type="family_match",
                    source="ai",
                    model_name="groq-test",
                    failure_cause=None,
                    payload={
                        "role_family_alignment": "same_family",
                        "seniority_alignment": "compatible",
                        "modifier_impact": "none",
                        "contradiction_strength": "none",
                    },
                )
            ],
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
        prompt="software engineer new grad",
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

    job = db_session.scalar(select(Job))
    tasks = db_session.scalars(select(JobRelevanceTask).order_by(JobRelevanceTask.id.asc())).all()
    evaluation_count = db_session.scalar(select(func.count(JobRelevanceEvaluation.id)))

    assert summary == {
        "processed": 1,
        "created": 1,
        "updated": 0,
        "pending_title_screening": 0,
        "pending_full_relevance": 1,
    }
    assert job is not None
    assert job.relevance_decision == "pending"
    assert job.relevance_source == "pending_full_relevance"
    assert evaluation_count == 0
    assert len(tasks) == 1
    assert tasks[0].phase == "full_relevance"
    assert tasks[0].payload["screening_decision"] == "pass"


def test_sync_source_inline_title_screening_writes_reject_for_out_of_scope_titles(db_session, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.tasks.job_relevance.classify_job_titles",
        lambda *args, **kwargs: JobTitleScreeningResult(
            items=[
                JobTitleScreeningItem(
                    title="Hardware Engineer",
                    decision="reject",
                    summary="The title appears to be a different role family.",
                    decision_rationale_type="clear_family_mismatch",
                    source="ai",
                    model_name="groq-test",
                    failure_cause=None,
                    payload={
                        "role_family_alignment": "different_family",
                        "seniority_alignment": "uncertain",
                        "modifier_impact": "material_scope_change",
                        "contradiction_strength": "strong",
                    },
                )
            ],
            source="ai",
            model_name="groq-test",
            failure_cause=None,
            payload={},
        ),
    )

    account = ensure_account(db_session, "owner@example.com")
    source = JobSource(
        account_id=account.id,
        source_key="simplify",
        source_type="github_curated",
        name="Simplify",
        base_url="https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/HEAD/README.md",
        settings_json={},
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

    markdown = """
<table>
<tbody>
<tr>
<td><strong><a href="https://simplify.jobs/c/HardwareCo">HardwareCo</a></strong></td>
<td>Hardware Engineer</td>
<td>San Jose, CA</td>
<td><a href="https://example.com/jobs/456">Apply</a></td>
</tr>
</tbody>
</table>
"""

    summary = sync_source(db_session, source.id, raw_payload=markdown)

    job = db_session.scalar(select(Job))
    tasks = db_session.scalars(select(JobRelevanceTask)).all()
    evaluations = db_session.scalars(select(JobRelevanceEvaluation)).all()

    assert summary == {
        "processed": 1,
        "created": 1,
        "updated": 0,
        "pending_title_screening": 0,
        "pending_full_relevance": 0,
    }
    assert job is not None
    assert job.relevance_decision == "reject"
    assert job.relevance_source == "title_screening"
    assert tasks == []
    assert len(evaluations) == 1
    assert evaluations[0].payload["decision_phase"] == "title_screening"


def test_sync_source_derives_greenhouse_board_token_from_base_url(db_session, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.tasks.discovery.drain_relevance_tasks_now",
        lambda session, account_id, title_batch_limit, full_batch_limit: {
            "title_screening_processed": 0,
            "full_relevance_processed": 0,
        },
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

    assert summary == {
        "processed": 1,
        "created": 1,
        "updated": 0,
        "pending_title_screening": 0,
        "pending_full_relevance": 0,
    }
    assert target is not None
    assert target.metadata_json["board_token"] == "alt"
