from __future__ import annotations

from app.domains.accounts.service import ensure_account
from app.domains.jobs.models import Job
from app.domains.questions.fingerprints import ApplyQuestion, fingerprint_question
from app.domains.questions.models import AnswerEntry, QuestionTask, QuestionTemplate


def _make_job(session, account_id: int, title: str = "Engineer") -> Job:
    job = Job(
        account_id=account_id,
        canonical_key=f"acme-{title.lower().replace(' ', '-')}",
        company_name="Acme",
        title=title,
        status="new",
    )
    session.add(job)
    session.flush()
    return job


def _make_template(session, account_id: int) -> QuestionTemplate:
    fp = fingerprint_question("Email address", "input_text", [])
    template = QuestionTemplate(
        account_id=account_id,
        fingerprint=fp,
        prompt_text="Email address",
        field_type="input_text",
        option_labels=[],
    )
    session.add(template)
    session.flush()
    return template


def _make_answer(session, account_id: int, template: QuestionTemplate) -> AnswerEntry:
    answer = AnswerEntry(
        account_id=account_id,
        question_template_id=template.id,
        label="My email",
        answer_text="user@example.com",
    )
    session.add(answer)
    session.flush()
    return answer


def _make_task(session, account_id: int, job: Job, template: QuestionTemplate, status: str = "new") -> QuestionTask:
    task = QuestionTask(
        account_id=account_id,
        job_id=job.id,
        question_template_id=template.id,
        question_fingerprint=template.fingerprint,
        prompt_text=template.prompt_text,
        field_type=template.field_type,
        option_labels=template.option_labels,
        status=status,
    )
    session.add(task)
    session.flush()
    return task


def test_resolving_task_auto_resolves_sibling_new_task(auth_client, db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    job_a = _make_job(db_session, account.id, "Engineer A")
    job_b = _make_job(db_session, account.id, "Engineer B")
    template = _make_template(db_session, account.id)
    answer = _make_answer(db_session, account.id, template)
    task_a = _make_task(db_session, account.id, job_a, template, status="new")
    task_b = _make_task(db_session, account.id, job_b, template, status="new")
    db_session.commit()

    resp = auth_client.patch(
        f"/api/questions/tasks/{task_a.id}/resolve",
        json={"status": "reusable", "linked_answer_entry_id": answer.id},
    )
    assert resp.status_code == 200

    db_session.expire_all()
    db_session.refresh(task_b)
    assert task_b.status == "reusable"
    assert task_b.linked_answer_entry_id == answer.id
    assert task_b.resolved_at is not None


def test_resolving_task_auto_resolves_sibling_pending_task(auth_client, db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    job_a = _make_job(db_session, account.id, "Engineer A")
    job_b = _make_job(db_session, account.id, "Engineer B")
    template = _make_template(db_session, account.id)
    answer = _make_answer(db_session, account.id, template)
    task_a = _make_task(db_session, account.id, job_a, template, status="new")
    task_b = _make_task(db_session, account.id, job_b, template, status="pending")
    db_session.commit()

    resp = auth_client.patch(
        f"/api/questions/tasks/{task_a.id}/resolve",
        json={"status": "reusable", "linked_answer_entry_id": answer.id},
    )
    assert resp.status_code == 200

    db_session.expire_all()
    db_session.refresh(task_b)
    assert task_b.status == "reusable"
    assert task_b.linked_answer_entry_id == answer.id


def test_get_tasks_returns_empty_after_sibling_resolution(auth_client, db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    job_a = _make_job(db_session, account.id, "Engineer A")
    job_b = _make_job(db_session, account.id, "Engineer B")
    template = _make_template(db_session, account.id)
    answer = _make_answer(db_session, account.id, template)
    task_a = _make_task(db_session, account.id, job_a, template, status="new")
    _make_task(db_session, account.id, job_b, template, status="new")
    db_session.commit()

    auth_client.patch(
        f"/api/questions/tasks/{task_a.id}/resolve",
        json={"status": "reusable", "linked_answer_entry_id": answer.id},
    )

    tasks_resp = auth_client.get("/api/questions/tasks")
    assert tasks_resp.status_code == 200
    assert tasks_resp.json() == []


def test_resolving_only_task_completes_without_error(auth_client, db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    job_a = _make_job(db_session, account.id, "Engineer A")
    template = _make_template(db_session, account.id)
    answer = _make_answer(db_session, account.id, template)
    task_a = _make_task(db_session, account.id, job_a, template, status="new")
    db_session.commit()

    resp = auth_client.patch(
        f"/api/questions/tasks/{task_a.id}/resolve",
        json={"status": "reusable", "linked_answer_entry_id": answer.id},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "reusable"


def test_sibling_already_reusable_not_overwritten(auth_client, db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    job_a = _make_job(db_session, account.id, "Engineer A")
    job_b = _make_job(db_session, account.id, "Engineer B")
    template = _make_template(db_session, account.id)
    answer_a = _make_answer(db_session, account.id, template)
    answer_b = AnswerEntry(
        account_id=account.id,
        question_template_id=template.id,
        label="Other email",
        answer_text="other@example.com",
    )
    db_session.add(answer_b)
    db_session.flush()
    task_a = _make_task(db_session, account.id, job_a, template, status="new")
    task_b = _make_task(db_session, account.id, job_b, template, status="reusable")
    task_b.linked_answer_entry_id = answer_b.id
    db_session.commit()

    auth_client.patch(
        f"/api/questions/tasks/{task_a.id}/resolve",
        json={"status": "reusable", "linked_answer_entry_id": answer_a.id},
    )

    db_session.expire_all()
    db_session.refresh(task_b)
    assert task_b.linked_answer_entry_id == answer_b.id


def test_sibling_resolved_task_not_touched(auth_client, db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    job_a = _make_job(db_session, account.id, "Engineer A")
    job_b = _make_job(db_session, account.id, "Engineer B")
    template = _make_template(db_session, account.id)
    answer = _make_answer(db_session, account.id, template)
    task_a = _make_task(db_session, account.id, job_a, template, status="new")
    task_b = _make_task(db_session, account.id, job_b, template, status="resolved")
    db_session.commit()

    auth_client.patch(
        f"/api/questions/tasks/{task_a.id}/resolve",
        json={"status": "reusable", "linked_answer_entry_id": answer.id},
    )

    db_session.expire_all()
    db_session.refresh(task_b)
    assert task_b.status == "resolved"
    assert task_b.linked_answer_entry_id is None


def test_sibling_resolution_scoped_to_account(auth_client, db_session) -> None:
    account1 = ensure_account(db_session, "owner@example.com")
    account2 = ensure_account(db_session, "other@example.com")

    job_a1 = _make_job(db_session, account1.id, "Engineer A1")
    job_a2 = _make_job(db_session, account2.id, "Engineer A2")

    fp = fingerprint_question("Email address", "input_text", [])
    template1 = QuestionTemplate(account_id=account1.id, fingerprint=fp, prompt_text="Email address", field_type="input_text", option_labels=[])
    template2 = QuestionTemplate(account_id=account2.id, fingerprint=fp, prompt_text="Email address", field_type="input_text", option_labels=[])
    db_session.add_all([template1, template2])
    db_session.flush()

    answer1 = _make_answer(db_session, account1.id, template1)
    task_a1 = _make_task(db_session, account1.id, job_a1, template1, status="new")
    task_a2 = _make_task(db_session, account2.id, job_a2, template2, status="new")
    db_session.commit()

    auth_client.patch(
        f"/api/questions/tasks/{task_a1.id}/resolve",
        json={"status": "reusable", "linked_answer_entry_id": answer1.id},
    )

    db_session.expire_all()
    db_session.refresh(task_a2)
    assert task_a2.status == "new"
