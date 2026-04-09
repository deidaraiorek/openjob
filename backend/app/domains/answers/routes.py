from __future__ import annotations

import shutil
from typing import Any
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
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


def ensure_question_template_belongs_to_account(
    *,
    question_template_id: int | None,
    current_account: Account,
    session: Session,
) -> None:
    if question_template_id is None:
        return

    template = session.scalar(
        select(QuestionTemplate).where(
            QuestionTemplate.id == question_template_id,
            QuestionTemplate.account_id == current_account.id,
        ),
    )
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question template not found",
        )


@router.post("", response_model=AnswerResponse, status_code=status.HTTP_201_CREATED)
def create_answer_entry(
    payload: AnswerCreateRequest,
    current_account: Account = Depends(get_current_account),
    session: Session = Depends(get_db_session),
) -> AnswerResponse:
    ensure_question_template_belongs_to_account(
        question_template_id=payload.question_template_id,
        current_account=current_account,
        session=session,
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


@router.post("/upload", response_model=AnswerResponse, status_code=status.HTTP_201_CREATED)
def upload_answer_file(
    question_template_id: int | None = Form(default=None),
    label: str = Form(default=""),
    upload: UploadFile = File(...),
    current_account: Account = Depends(get_current_account),
    session: Session = Depends(get_db_session),
) -> AnswerResponse:
    ensure_question_template_belongs_to_account(
        question_template_id=question_template_id,
        current_account=current_account,
        session=session,
    )

    original_filename = (upload.filename or "").strip()
    if not original_filename:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Uploaded file must have a filename",
        )

    suffix = Path(original_filename).suffix
    storage_root = Path(get_settings().answer_file_storage_dir) / str(current_account.id)
    storage_root.mkdir(parents=True, exist_ok=True)
    storage_path = storage_root / f"{uuid4().hex}{suffix}"

    with storage_path.open("wb") as destination:
        shutil.copyfileobj(upload.file, destination)

    size_bytes = storage_path.stat().st_size
    answer_entry = AnswerEntry(
        account_id=current_account.id,
        question_template_id=question_template_id,
        label=label.strip() or Path(original_filename).stem or "Uploaded file",
        answer_text=None,
        answer_payload={
            "kind": "file",
            "filename": original_filename,
            "mime_type": upload.content_type or "application/octet-stream",
            "size_bytes": size_bytes,
            "stored_path": str(storage_path),
        },
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

    ensure_question_template_belongs_to_account(
        question_template_id=payload.question_template_id,
        current_account=current_account,
        session=session,
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
