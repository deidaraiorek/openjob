from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.domains.accounts.dependencies import get_current_account
from app.domains.accounts.models import Account
from app.domains.questions.models import AnswerEntry, QuestionAlias, QuestionTask, QuestionTemplate
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
    placeholder_text: str | None
    required: bool
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
        placeholder_text=task.placeholder_text,
        required=task.required,
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
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Question task not found")

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
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="Answer entry not found",
            )

    if payload.status == "reusable" and answer_entry is None:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
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

    if payload.status == "reusable" and answer_entry is not None:
        session.execute(
            update(QuestionTask)
            .where(
                QuestionTask.account_id == current_account.id,
                QuestionTask.question_fingerprint == task.question_fingerprint,
                QuestionTask.status.in_(UNRESOLVED_TASK_STATUSES),
                QuestionTask.id != task.id,
            )
            .values(
                status="reusable",
                linked_answer_entry_id=answer_entry.id,
                resolved_at=datetime.now(UTC),
            )
        )
        session.execute(
            update(QuestionAlias)
            .where(
                QuestionAlias.account_id == current_account.id,
                QuestionAlias.source_fingerprint == task.question_fingerprint,
                QuestionAlias.status == "suggested",
            )
            .values(status="rejected")
        )

    session.commit()
    session.refresh(task)
    return serialize_question_task(task)


class QuestionAliasResponse(BaseModel):
    id: int
    source_fingerprint: str
    canonical_fingerprint: str
    source_prompt: str
    canonical_prompt: str
    status: str
    similarity_score: float


class UpdateAliasRequest(BaseModel):
    status: str


@router.get("/aliases", response_model=list[QuestionAliasResponse])
def list_question_aliases(
    status: str = "suggested",
    current_account: Account = Depends(get_current_account),
    session: Session = Depends(get_db_session),
) -> list[QuestionAliasResponse]:
    aliases = session.scalars(
        select(QuestionAlias).where(
            QuestionAlias.account_id == current_account.id,
            QuestionAlias.status == status,
        )
    ).all()

    result = []
    for alias in aliases:
        source_template = session.scalar(
            select(QuestionTemplate).where(
                QuestionTemplate.account_id == current_account.id,
                QuestionTemplate.fingerprint == alias.source_fingerprint,
            )
        )
        canonical_template = session.scalar(
            select(QuestionTemplate).where(
                QuestionTemplate.account_id == current_account.id,
                QuestionTemplate.fingerprint == alias.canonical_fingerprint,
            )
        )
        result.append(QuestionAliasResponse(
            id=alias.id,
            source_fingerprint=alias.source_fingerprint,
            canonical_fingerprint=alias.canonical_fingerprint,
            source_prompt=source_template.prompt_text if source_template else alias.source_fingerprint,
            canonical_prompt=canonical_template.prompt_text if canonical_template else alias.canonical_fingerprint,
            status=alias.status,
            similarity_score=alias.similarity_score,
        ))
    return result


@router.patch("/aliases/{alias_id}", response_model=QuestionAliasResponse)
def update_question_alias(
    alias_id: int,
    payload: UpdateAliasRequest,
    current_account: Account = Depends(get_current_account),
    session: Session = Depends(get_db_session),
) -> QuestionAliasResponse:
    if payload.status not in {"approved", "rejected"}:
        raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT, detail="status must be 'approved' or 'rejected'")

    alias = session.scalar(
        select(QuestionAlias).where(
            QuestionAlias.id == alias_id,
            QuestionAlias.account_id == current_account.id,
        )
    )
    if not alias:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Alias not found")

    if payload.status == "approved":
        loop_check_1 = session.scalar(
            select(QuestionAlias).where(
                QuestionAlias.account_id == current_account.id,
                QuestionAlias.source_fingerprint == alias.canonical_fingerprint,
                QuestionAlias.status == "approved",
            )
        )
        loop_check_2 = session.scalar(
            select(QuestionAlias).where(
                QuestionAlias.account_id == current_account.id,
                QuestionAlias.canonical_fingerprint == alias.source_fingerprint,
                QuestionAlias.status == "approved",
            )
        )
        if loop_check_1 or loop_check_2:
            raise HTTPException(
                status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Approving this alias would create an alias chain, which is not allowed",
            )

        canonical_template = session.scalar(
            select(QuestionTemplate).where(
                QuestionTemplate.account_id == current_account.id,
                QuestionTemplate.fingerprint == alias.canonical_fingerprint,
            )
        )
        if canonical_template:
            session.execute(
                update(QuestionTask)
                .where(
                    QuestionTask.account_id == current_account.id,
                    QuestionTask.question_fingerprint == alias.source_fingerprint,
                )
                .values(
                    question_fingerprint=alias.canonical_fingerprint,
                    question_template_id=canonical_template.id,
                )
            )

    alias.status = payload.status
    session.commit()
    session.refresh(alias)

    source_template = session.scalar(
        select(QuestionTemplate).where(
            QuestionTemplate.account_id == current_account.id,
            QuestionTemplate.fingerprint == alias.source_fingerprint,
        )
    )
    canonical_template = session.scalar(
        select(QuestionTemplate).where(
            QuestionTemplate.account_id == current_account.id,
            QuestionTemplate.fingerprint == alias.canonical_fingerprint,
        )
    )
    return QuestionAliasResponse(
        id=alias.id,
        source_fingerprint=alias.source_fingerprint,
        canonical_fingerprint=alias.canonical_fingerprint,
        source_prompt=source_template.prompt_text if source_template else alias.source_fingerprint,
        canonical_prompt=canonical_template.prompt_text if canonical_template else alias.canonical_fingerprint,
        status=alias.status,
        similarity_score=alias.similarity_score,
    )


@router.get("/tasks", response_model=list[QuestionTaskResponse])
def list_question_tasks(
    current_account: Account = Depends(get_current_account),
    session: Session = Depends(get_db_session),
    job_id: int | None = None,
) -> list[QuestionTaskResponse]:
    filters = [
        QuestionTask.account_id == current_account.id,
        QuestionTask.status.in_(UNRESOLVED_TASK_STATUSES),
    ]
    if job_id is not None:
        filters.append(QuestionTask.job_id == job_id)
    tasks = session.scalars(
        select(QuestionTask)
        .where(*filters)
        .order_by(QuestionTask.id.asc()),
    ).all()
    return [serialize_question_task(task) for task in tasks]
