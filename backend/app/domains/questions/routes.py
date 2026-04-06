from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.accounts.dependencies import get_current_account
from app.domains.accounts.models import Account
from app.domains.questions.models import AnswerEntry, QuestionTask
from app.db.session import get_db_session

router = APIRouter(prefix="/questions", tags=["questions"])
UNRESOLVED_TASK_STATUSES = {"new", "pending"}


class QuestionTaskResponse(BaseModel):
    id: int
    question_template_id: int | None
    question_fingerprint: str
    prompt_text: str
    field_type: str
    option_labels: list[str]
    status: str
    linked_answer_entry_id: int | None


class ResolveQuestionTaskRequest(BaseModel):
    status: str
    linked_answer_entry_id: int | None = None


def serialize_question_task(task: QuestionTask) -> QuestionTaskResponse:
    return QuestionTaskResponse(
        id=task.id,
        question_template_id=task.question_template_id,
        question_fingerprint=task.question_fingerprint,
        prompt_text=task.prompt_text,
        field_type=task.field_type,
        option_labels=task.option_labels,
        status=task.status,
        linked_answer_entry_id=task.linked_answer_entry_id,
    )


@router.patch("/tasks/{task_id}/resolve", response_model=QuestionTaskResponse)
def resolve_question_task(
    task_id: int,
    payload: ResolveQuestionTaskRequest,
    current_account: Account = Depends(get_current_account),
    session: Session = Depends(get_db_session),
) -> QuestionTaskResponse:
    task = session.scalar(
        select(QuestionTask).where(
            QuestionTask.id == task_id,
            QuestionTask.account_id == current_account.id,
        ),
    )
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question task not found")

    answer_entry: AnswerEntry | None = None
    if payload.linked_answer_entry_id is not None:
        answer_entry = session.scalar(
            select(AnswerEntry).where(
                AnswerEntry.id == payload.linked_answer_entry_id,
                AnswerEntry.account_id == current_account.id,
            ),
        )
        if not answer_entry:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Answer entry not found",
            )

    if payload.status == "reusable" and answer_entry is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Reusable question tasks must be linked to an answer entry",
        )

    if (
        payload.status == "reusable"
        and answer_entry is not None
        and answer_entry.question_template_id is None
        and task.question_template_id is not None
    ):
        answer_entry.question_template_id = task.question_template_id

    task.status = payload.status
    task.linked_answer_entry_id = answer_entry.id if answer_entry else None
    task.resolved_at = datetime.now(UTC) if payload.status in {"resolved", "reusable"} else None

    session.commit()
    session.refresh(task)
    return serialize_question_task(task)


@router.get("/tasks", response_model=list[QuestionTaskResponse])
def list_question_tasks(
    current_account: Account = Depends(get_current_account),
    session: Session = Depends(get_db_session),
) -> list[QuestionTaskResponse]:
    tasks = session.scalars(
        select(QuestionTask)
        .where(
            QuestionTask.account_id == current_account.id,
            QuestionTask.status.in_(UNRESOLVED_TASK_STATUSES),
        )
        .order_by(QuestionTask.id.asc()),
    ).all()
    return [serialize_question_task(task) for task in tasks]
