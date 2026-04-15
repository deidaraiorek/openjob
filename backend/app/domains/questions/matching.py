from __future__ import annotations

import difflib
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.domains.questions.fingerprints import ApplyQuestion, fingerprint_apply_question
from app.domains.questions.models import AnswerEntry, QuestionAlias, QuestionTask, QuestionTemplate

_ALIAS_SIMILARITY_THRESHOLD = 0.6


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


def resolve_alias(session: Session, account_id: int, fingerprint: str) -> str:
    alias = session.scalar(
        select(QuestionAlias).where(
            QuestionAlias.account_id == account_id,
            QuestionAlias.source_fingerprint == fingerprint,
            QuestionAlias.status == "approved",
        )
    )
    return alias.canonical_fingerprint if alias else fingerprint


def _generate_alias_suggestions(session: Session, account_id: int, new_template: QuestionTemplate) -> None:
    existing = session.scalars(
        select(QuestionTemplate).where(
            QuestionTemplate.account_id == account_id,
            QuestionTemplate.id != new_template.id,
            QuestionTemplate.field_type == new_template.field_type,
        )
    ).all()

    new_prompt = new_template.prompt_text.lower().strip()
    for other in existing:
        other_prompt = other.prompt_text.lower().strip()
        score = difflib.SequenceMatcher(None, new_prompt, other_prompt).ratio()
        if score < _ALIAS_SIMILARITY_THRESHOLD:
            continue

        source_fp = new_template.fingerprint
        canonical_fp = other.fingerprint

        already_exists = session.scalar(
            select(QuestionAlias).where(
                QuestionAlias.account_id == account_id,
                QuestionAlias.source_fingerprint == source_fp,
            )
        )
        if already_exists:
            continue

        session.add(
            QuestionAlias(
                account_id=account_id,
                source_fingerprint=source_fp,
                canonical_fingerprint=canonical_fp,
                status="suggested",
                similarity_score=score,
            )
        )
    session.flush()


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
    _generate_alias_suggestions(session, account_id, template)
    return template


def _resolve_ranked_answer(answer_entry: AnswerEntry, option_labels: list[str]) -> AnswerEntry | None:
    ranked = answer_entry.answer_payload.get("ranked_options")
    if ranked is None:
        return answer_entry
    lower_options = {o.lower() for o in option_labels}
    for preferred in ranked:
        if preferred.lower() in lower_options:
            matched = next(o for o in option_labels if o.lower() == preferred.lower())
            synthetic = AnswerEntry(
                account_id=answer_entry.account_id,
                question_template_id=answer_entry.question_template_id,
                label=answer_entry.label,
                answer_text=matched,
                answer_payload={"value": matched},
            )
            return synthetic
    return None


def resolve_questions(
    session: Session,
    account_id: int,
    questions: list[ApplyQuestion],
) -> list[ResolvedQuestion]:
    resolved: list[ResolvedQuestion] = []

    for question in questions:
        canonical_fingerprint = resolve_alias(session, account_id, fingerprint_apply_question(question))
        if canonical_fingerprint != fingerprint_apply_question(question):
            template = session.scalar(
                select(QuestionTemplate).where(
                    QuestionTemplate.account_id == account_id,
                    QuestionTemplate.fingerprint == canonical_fingerprint,
                )
            ) or ensure_question_template(session, account_id, question)
        else:
            template = ensure_question_template(session, account_id, question)
        answer_entry = session.scalar(
            select(AnswerEntry)
            .where(
                AnswerEntry.account_id == account_id,
                AnswerEntry.question_template_id == template.id,
            )
            .order_by(AnswerEntry.created_at.desc()),
        )

        if answer_entry and "ranked_options" in (answer_entry.answer_payload or {}):
            answer_entry = _resolve_ranked_answer(answer_entry, question.option_labels)

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
            QuestionTask.status.in_(["new", "pending"]),
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
