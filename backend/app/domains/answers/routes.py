from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.accounts.dependencies import get_current_account
from app.domains.accounts.models import Account
from app.domains.questions.models import AnswerEntry, QuestionTemplate
from app.db.session import get_db_session

router = APIRouter(prefix="/answers", tags=["answers"])


class AnswerCreateRequest(BaseModel):
    question_template_id: int | None = None
    label: str = "Default answer"
    answer_text: str | None = None
    answer_payload: dict[str, Any] = Field(default_factory=dict)


class AnswerUpdateRequest(BaseModel):
    question_template_id: int | None = None
    label: str = "Default answer"
    answer_text: str | None = None
    answer_payload: dict[str, Any] = Field(default_factory=dict)


class AnswerResponse(BaseModel):
    id: int
    question_template_id: int | None
    label: str
    answer_text: str | None
    answer_payload: dict[str, Any]


def serialize_answer(answer_entry: AnswerEntry) -> AnswerResponse:
    return AnswerResponse(
        id=answer_entry.id,
        question_template_id=answer_entry.question_template_id,
        label=answer_entry.label,
        answer_text=answer_entry.answer_text,
        answer_payload=answer_entry.answer_payload,
    )


@router.post("", response_model=AnswerResponse, status_code=status.HTTP_201_CREATED)
def create_answer_entry(
    payload: AnswerCreateRequest,
    current_account: Account = Depends(get_current_account),
    session: Session = Depends(get_db_session),
) -> AnswerResponse:
    if payload.question_template_id is not None:
        template = session.scalar(
            select(QuestionTemplate).where(
                QuestionTemplate.id == payload.question_template_id,
                QuestionTemplate.account_id == current_account.id,
            ),
        )
        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Question template not found",
            )

    answer_entry = AnswerEntry(
        account_id=current_account.id,
        question_template_id=payload.question_template_id,
        label=payload.label,
        answer_text=payload.answer_text,
        answer_payload=payload.answer_payload,
    )
    session.add(answer_entry)
    session.commit()
    session.refresh(answer_entry)
    return serialize_answer(answer_entry)


@router.put("/{answer_id}", response_model=AnswerResponse)
def update_answer_entry(
    answer_id: int,
    payload: AnswerUpdateRequest,
    current_account: Account = Depends(get_current_account),
    session: Session = Depends(get_db_session),
) -> AnswerResponse:
    answer_entry = session.scalar(
        select(AnswerEntry).where(
            AnswerEntry.id == answer_id,
            AnswerEntry.account_id == current_account.id,
        ),
    )
    if not answer_entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Answer entry not found")

    if payload.question_template_id is not None:
        template = session.scalar(
            select(QuestionTemplate).where(
                QuestionTemplate.id == payload.question_template_id,
                QuestionTemplate.account_id == current_account.id,
            ),
        )
        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Question template not found",
            )

    answer_entry.question_template_id = payload.question_template_id
    answer_entry.label = payload.label
    answer_entry.answer_text = payload.answer_text
    answer_entry.answer_payload = payload.answer_payload
    session.commit()
    session.refresh(answer_entry)
    return serialize_answer(answer_entry)


@router.get("", response_model=list[AnswerResponse])
def list_answer_entries(
    current_account: Account = Depends(get_current_account),
    session: Session = Depends(get_db_session),
) -> list[AnswerResponse]:
    answer_entries = session.scalars(
        select(AnswerEntry)
        .where(AnswerEntry.account_id == current_account.id)
        .order_by(AnswerEntry.id.asc()),
    ).all()
    return [serialize_answer(answer_entry) for answer_entry in answer_entries]
