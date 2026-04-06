from __future__ import annotations

from sqlalchemy import select

from app.celery_app import celery_app
from app.db.session import get_session_factory
from app.domains.accounts.models import Account
from app.domains.applications.service import execute_application_run


@celery_app.task(name="app.tasks.applications.run_application")
def run_application(job_id: int, account_email: str = "owner@example.com") -> dict[str, object]:
    session_factory = get_session_factory()
    with session_factory() as session:
        account = session.scalar(select(Account).where(Account.email == account_email))
        if not account:
            raise ValueError(f"Unknown account: {account_email}")

        result = execute_application_run(session, account=account, job_id=job_id)
        return {
            "application_run_id": result.application_run_id,
            "status": result.status,
            "answer_entry_ids": result.answer_entry_ids,
            "created_question_task_ids": result.created_question_task_ids,
        }
