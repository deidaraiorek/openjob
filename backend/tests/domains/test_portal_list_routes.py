from app.domains.accounts.service import ensure_account
from app.domains.applications.models import ApplicationRun
from app.domains.answers.routes import serialize_answer
from app.domains.jobs.models import ApplyTarget, Job
from app.domains.questions.models import AnswerEntry, QuestionTask, QuestionTemplate


def test_portal_list_routes_return_jobs_answers_and_question_tasks(auth_client, db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    job = Job(
        account_id=account.id,
        canonical_key="acme-frontend-engineer-i",
        company_name="Acme",
        title="Frontend Engineer I",
        location="Remote",
        status="blocked_missing_answer",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    template = QuestionTemplate(
        account_id=account.id,
        fingerprint="portfolio url::input_text::",
        prompt_text="Portfolio URL",
        field_type="input_text",
        option_labels=[],
    )
    answer = AnswerEntry(
        account_id=account.id,
        question_template=template,
        label="Portfolio URL",
        answer_text="https://example.com",
    )
    question_task = QuestionTask(
        account_id=account.id,
        job_id=job.id,
        question_template=template,
        question_fingerprint=template.fingerprint,
        prompt_text="Portfolio URL",
        field_type="input_text",
        option_labels=[],
        status="new",
    )
    apply_target = ApplyTarget(
        job_id=job.id,
        target_type="greenhouse_apply",
        destination_url="https://boards.greenhouse.io/acme/jobs/1200",
        is_preferred=True,
        metadata_json={},
    )
    db_session.add_all([template, answer, question_task, apply_target])
    db_session.commit()
    db_session.add(
        ApplicationRun(
            account_id=account.id,
            job_id=job.id,
            apply_target_id=apply_target.id,
            status="submitted",
        )
    )
    db_session.commit()

    jobs_response = auth_client.get("/api/jobs")
    answers_response = auth_client.get("/api/answers")
    tasks_response = auth_client.get("/api/questions/tasks")

    assert jobs_response.status_code == 200
    assert jobs_response.json()[0]["company_name"] == "Acme"
    assert jobs_response.json()[0]["preferred_apply_target_type"] == "greenhouse_apply"
    assert jobs_response.json()[0]["open_question_task_count"] == 1
    assert jobs_response.json()[0]["latest_application_run_status"] == "submitted"

    assert answers_response.status_code == 200
    assert answers_response.json()[0]["label"] == serialize_answer(answer).label

    assert tasks_response.status_code == 200
    assert tasks_response.json()[0]["prompt_text"] == "Portfolio URL"


def test_portal_job_list_hides_rejected_jobs_from_active_view(auth_client, db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    db_session.add_all(
        [
            Job(
                account_id=account.id,
                canonical_key="visible-job",
                company_name="Acme",
                title="Software Engineer I",
                location="Remote",
                status="discovered",
            ),
            Job(
                account_id=account.id,
                canonical_key="hidden-job",
                company_name="HardwareCo",
                title="Hardware Engineer",
                location="San Jose, CA",
                status="discovered",
                relevance_decision="reject",
                relevance_source="ai",
                relevance_summary="Rejected as a hardware role.",
            ),
        ]
    )
    db_session.commit()

    jobs_response = auth_client.get("/api/jobs")

    assert jobs_response.status_code == 200
    assert [job["title"] for job in jobs_response.json()] == ["Software Engineer I"]


def test_portal_job_list_includes_rejected_jobs_in_reject_view(auth_client, db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    db_session.add_all(
        [
            Job(
                account_id=account.id,
                canonical_key="visible-job",
                company_name="Acme",
                title="Software Engineer I",
                location="Remote",
                status="discovered",
            ),
            Job(
                account_id=account.id,
                canonical_key="rejected-job",
                company_name="HardwareCo",
                title="Hardware Engineer",
                location="San Jose, CA",
                status="filtered_out",
                relevance_decision="reject",
                relevance_source="title_gate",
                relevance_summary="title not matched",
            ),
        ]
    )
    db_session.commit()

    jobs_response = auth_client.get("/api/jobs?relevance=reject")

    assert jobs_response.status_code == 200
    assert [job["title"] for job in jobs_response.json()] == ["Hardware Engineer"]


def test_question_queue_hides_reusable_tasks(auth_client, db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    job = Job(
        account_id=account.id,
        canonical_key="question-queue-job",
        company_name="Acme",
        title="Software Engineer I",
        location="Remote",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    db_session.add_all(
        [
            QuestionTask(
                account_id=account.id,
                job_id=job.id,
                question_fingerprint="first-name",
                prompt_text="First Name",
                field_type="input_text",
                option_labels=[],
                status="reusable",
            ),
            QuestionTask(
                account_id=account.id,
                job_id=job.id,
                question_fingerprint="last-name",
                prompt_text="Last Name",
                field_type="input_text",
                option_labels=[],
                status="new",
            ),
        ]
    )
    db_session.commit()

    tasks_response = auth_client.get("/api/questions/tasks")

    assert tasks_response.status_code == 200
    assert [task["prompt_text"] for task in tasks_response.json()] == ["Last Name"]
