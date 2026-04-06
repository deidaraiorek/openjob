from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.domains.questions.fingerprints import ApplyQuestion, fingerprint_apply_question
from app.domains.questions.models import AnswerEntry, QuestionTask, QuestionTemplate


@dataclass(slots=True)
class ResolvedQuestion:
    question: ApplyQuestion
    fingerprint: str
    template: QuestionTemplate
    answer_entry: AnswerEntry | None

    @property
    def answer_value(self):
        if not self.answer_entry:
            return None
        if self.answer_entry.answer_payload:
            if "values" in self.answer_entry.answer_payload:
                return self.answer_entry.answer_payload["values"]
            if "value" in self.answer_entry.answer_payload:
                return self.answer_entry.answer_payload["value"]
            return self.answer_entry.answer_payload
        return self.answer_entry.answer_text


def ensure_question_template(
    session: Session,
    account_id: int,
    question: ApplyQuestion,
) -> QuestionTemplate:
    fingerprint = fingerprint_apply_question(question)
    template = session.scalar(
        select(QuestionTemplate).where(
            QuestionTemplate.account_id == account_id,
            QuestionTemplate.fingerprint == fingerprint,
        ),
    )
    if template:
        return template

    template = QuestionTemplate(
        account_id=account_id,
        fingerprint=fingerprint,
        prompt_text=question.prompt_text,
        field_type=question.field_type,
        option_labels=question.option_labels,
    )
    session.add(template)
    session.flush()
    return template


def resolve_questions(
    session: Session,
    account_id: int,
    questions: list[ApplyQuestion],
) -> list[ResolvedQuestion]:
    resolved: list[ResolvedQuestion] = []

    for question in questions:
        template = ensure_question_template(session, account_id, question)
        answer_entry = session.scalar(
            select(AnswerEntry).where(
                AnswerEntry.account_id == account_id,
                AnswerEntry.question_template_id == template.id,
            ),
        )
        resolved.append(
            ResolvedQuestion(
                question=question,
                fingerprint=template.fingerprint,
                template=template,
                answer_entry=answer_entry,
            ),
        )

    return resolved


def ensure_question_task(
    session: Session,
    *,
    account_id: int,
    job_id: int,
    application_run_id: int,
    resolved_question: ResolvedQuestion,
) -> QuestionTask:
    existing = session.scalar(
        select(QuestionTask).where(
            QuestionTask.account_id == account_id,
            QuestionTask.job_id == job_id,
            QuestionTask.question_fingerprint == resolved_question.fingerprint,
            QuestionTask.status.in_(["new", "pending", "reusable"]),
        ),
    )
    if existing:
        existing.application_run_id = application_run_id
        existing.prompt_text = resolved_question.question.prompt_text
        existing.field_type = resolved_question.question.field_type
        existing.option_labels = resolved_question.question.option_labels
        return existing

    task = QuestionTask(
        account_id=account_id,
        job_id=job_id,
        application_run_id=application_run_id,
        question_template_id=resolved_question.template.id,
        question_fingerprint=resolved_question.fingerprint,
        prompt_text=resolved_question.question.prompt_text,
        field_type=resolved_question.question.field_type,
        option_labels=resolved_question.question.option_labels,
        status="new",
        resolved_at=None,
    )
    session.add(task)
    session.flush()
    return task


def mark_question_task_resolved(session: Session, task: QuestionTask, answer_entry: AnswerEntry) -> None:
    task.linked_answer_entry_id = answer_entry.id
    task.status = "reusable"
    task.resolved_at = utcnow()
