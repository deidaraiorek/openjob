from fastapi.testclient import TestClient

from app.domains.accounts.service import ensure_account
from app.domains.jobs.models import Job
from app.domains.questions.models import AnswerEntry, QuestionTask


def test_reusable_question_requires_linked_answer_entry(
    auth_client: TestClient,
    db_session,
) -> None:
    account = ensure_account(db_session, "owner@example.com")
    job = Job(
        account_id=account.id,
        canonical_key="acme-software-engineer-i",
        company_name="Acme",
        title="Software Engineer I",
        location="Remote",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    task = QuestionTask(
        account_id=account.id,
        job_id=job.id,
        question_fingerprint="citizenship-radio",
        prompt_text="Are you authorized to work in the US?",
        field_type="radio",
        option_labels=["Yes", "No"],
        status="new",
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    response = auth_client.patch(
        f"/api/questions/tasks/{task.id}/resolve",
        json={"status": "reusable"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Reusable question tasks must be linked to an answer entry"


def test_question_task_can_be_marked_reusable_with_answer_entry(
    auth_client: TestClient,
    db_session,
) -> None:
    account = ensure_account(db_session, "owner@example.com")
    job = Job(
        account_id=account.id,
        canonical_key="acme-platform-engineer-i",
        company_name="Acme",
        title="Platform Engineer I",
        location="New York, NY",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    answer = AnswerEntry(
        account_id=account.id,
        label="US work authorization",
        answer_text="Yes",
    )
    task = QuestionTask(
        account_id=account.id,
        job_id=job.id,
        question_fingerprint="work-auth",
        prompt_text="Are you authorized to work in the US?",
        field_type="radio",
        option_labels=["Yes", "No"],
        status="new",
    )
    db_session.add_all([answer, task])
    db_session.commit()
    db_session.refresh(answer)
    db_session.refresh(task)

    response = auth_client.patch(
        f"/api/questions/tasks/{task.id}/resolve",
        json={"status": "reusable", "linked_answer_entry_id": answer.id},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "reusable"
    assert response.json()["linked_answer_entry_id"] == answer.id
