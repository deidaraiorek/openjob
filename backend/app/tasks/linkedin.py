from __future__ import annotations

from sqlalchemy import select

from app.celery_app import celery_app
from app.db.session import get_session_factory
from app.domains.accounts.models import Account
from app.integrations.linkedin.apply import execute_linkedin_application_run
from app.tasks.discovery import sync_source


@celery_app.task(name="app.tasks.linkedin.sync_source")
def sync_linkedin_source(source_id: int, raw_payload: dict | None = None) -> dict[str, int]:
    session_factory = get_session_factory()
    with session_factory() as session:
        return sync_source(session, source_id, raw_payload=raw_payload)


@celery_app.task(name="app.tasks.linkedin.run_application")
def run_linkedin_application(job_id: int, account_email: str = "owner@example.com") -> dict[str, object]:
    session_factory = get_session_factory()
    with session_factory() as session:
        account = session.scalar(select(Account).where(Account.email == account_email))
        if not account:
            raise ValueError(f"Unknown account: {account_email}")

        result = execute_linkedin_application_run(session, account=account, job_id=job_id)
        return {
            "application_run_id": result.application_run_id,
            "status": result.status,
            "answer_entry_ids": result.answer_entry_ids,
            "created_question_task_ids": result.created_question_task_ids,
        }
