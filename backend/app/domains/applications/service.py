from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.base import utcnow
from app.domains.accounts.models import Account
from app.domains.applications.models import ApplicationEvent, ApplicationRun
from app.domains.applications.redaction import redact_payload
from app.domains.applications.retry_policy import (
    ActionNeededApplyError,
    RetryableApplyError,
    TerminalApplyError,
    classify_apply_exception,
)
from app.domains.jobs.models import ApplyTarget, Job
from app.domains.questions.matching import ensure_question_task, resolve_questions
from app.integrations.greenhouse import apply as greenhouse_apply
from app.integrations.lever import apply as lever_apply


@dataclass(slots=True)
class ApplyResult:
    application_run_id: int
    status: str
    answer_entry_ids: list[int]
    created_question_task_ids: list[int]


FetchQuestionsFn = Callable[[ApplyTarget], Any]
SubmitFn = Callable[[ApplyTarget, dict[str, Any]], dict[str, Any]]


def _log_event(run: ApplicationRun, event_type: str, payload: dict[str, Any]) -> None:
    run.events.append(ApplicationEvent(event_type=event_type, payload=payload))


def _default_fetch_questions(apply_target: ApplyTarget):
    if apply_target.target_type == "greenhouse_apply":
        board_token = apply_target.metadata_json["board_token"]
        job_post_id = apply_target.metadata_json["job_post_id"]
        return greenhouse_apply.fetch_question_payload(board_token, job_post_id)
    if apply_target.target_type == "lever_apply":
        posting_id = apply_target.metadata_json["posting_id"]
        return lever_apply.fetch_question_payload(posting_id)
    raise TerminalApplyError(f"Unsupported apply target: {apply_target.target_type}")


def _default_submit(apply_target: ApplyTarget, payload: dict[str, Any]) -> dict[str, Any]:
    if apply_target.target_type == "greenhouse_apply":
        try:
            return greenhouse_apply.submit_application(
                board_token=apply_target.metadata_json["board_token"],
                job_post_id=apply_target.metadata_json["job_post_id"],
                api_key=apply_target.metadata_json["api_key"],
                submission_payload=payload,
            )
        except Exception as error:  # pragma: no cover - real network path
            raise RetryableApplyError(str(error)) from error
    if apply_target.target_type == "lever_apply":
        try:
            return lever_apply.submit_application(
                posting_id=apply_target.metadata_json["posting_id"],
                api_key=apply_target.metadata_json["api_key"],
                submission_payload=payload,
            )
        except Exception as error:  # pragma: no cover - real network path
            raise RetryableApplyError(str(error)) from error
    raise TerminalApplyError(f"Unsupported apply target: {apply_target.target_type}")


def _parse_questions(apply_target: ApplyTarget, payload: Any):
    if apply_target.target_type == "greenhouse_apply":
        return greenhouse_apply.parse_question_payload(payload)
    if apply_target.target_type == "lever_apply":
        return lever_apply.parse_question_payload(payload)
    raise TerminalApplyError(f"Unsupported apply target: {apply_target.target_type}")


def _build_submission_payload(
    apply_target: ApplyTarget,
    *,
    questions,
    answers_by_key: dict[str, Any],
) -> dict[str, Any]:
    if apply_target.target_type == "greenhouse_apply":
        return greenhouse_apply.build_submission_payload(questions, answers_by_key)
    if apply_target.target_type == "lever_apply":
        return lever_apply.build_submission_payload(questions, answers_by_key)
    raise TerminalApplyError(f"Unsupported apply target: {apply_target.target_type}")


def _select_preferred_apply_target(job: Job) -> ApplyTarget:
    preferred = next((target for target in job.apply_targets if target.is_preferred), None)
    if preferred:
        return preferred
    if job.apply_targets:
        return job.apply_targets[0]
    raise TerminalApplyError("Job does not have an apply target")


def execute_application_run(
    session: Session,
    *,
    account: Account,
    job_id: int,
    fetch_questions: FetchQuestionsFn | None = None,
    submit_application: SubmitFn | None = None,
) -> ApplyResult:
    job = session.scalar(
        select(Job)
        .where(Job.id == job_id, Job.account_id == account.id)
        .options(
            selectinload(Job.apply_targets),
            selectinload(Job.question_tasks),
        ),
    )
    if not job:
        raise TerminalApplyError("Job not found")

    apply_target = _select_preferred_apply_target(job)
    run = ApplicationRun(
        account_id=account.id,
        job_id=job.id,
        apply_target_id=apply_target.id,
        status="queued",
    )
    session.add(run)
    session.flush()
    _log_event(
        run,
        "queued",
        {"apply_target_id": apply_target.id, "target_type": apply_target.target_type},
    )

    fetcher = fetch_questions or _default_fetch_questions
    submitter = submit_application or _default_submit

    try:
        question_payload = fetcher(apply_target)
        questions = _parse_questions(apply_target, question_payload)
        _log_event(run, "questions_fetched", {"question_count": len(questions)})

        resolved_questions = resolve_questions(session, account.id, questions)
        answer_entry_ids = [
            item.answer_entry.id
            for item in resolved_questions
            if item.answer_entry is not None
        ]

        unresolved_required = [
            item for item in resolved_questions if item.question.required and item.answer_entry is None
        ]
        if unresolved_required:
            task_ids = [
                ensure_question_task(
                    session,
                    account_id=account.id,
                    job_id=job.id,
                    application_run_id=run.id,
                    resolved_question=item,
                ).id
                for item in unresolved_required
            ]
            run.status = "blocked_missing_answer"
            run.completed_at = utcnow()
            _log_event(
                run,
                "blocked_missing_answer",
                {
                    "question_task_ids": task_ids,
                    "question_fingerprints": [item.fingerprint for item in unresolved_required],
                },
            )
            session.commit()
            return ApplyResult(
                application_run_id=run.id,
                status=run.status,
                answer_entry_ids=answer_entry_ids,
                created_question_task_ids=task_ids,
            )

        answers_by_key = {
            item.question.key: item.answer_value
            for item in resolved_questions
            if item.answer_entry is not None
        }
        submission_payload = _build_submission_payload(
            apply_target,
            questions=questions,
            answers_by_key=answers_by_key,
        )
        redacted_payload = redact_payload(submission_payload)
        submit_response = submitter(apply_target, submission_payload)
        run.status = "submitted"
        run.completed_at = utcnow()
        _log_event(
            run,
            "submitted",
            {
                "answer_entry_ids": answer_entry_ids,
                "submission_payload": redacted_payload,
                "submit_response": redact_payload(submit_response),
            },
        )
        session.commit()
        return ApplyResult(
            application_run_id=run.id,
            status=run.status,
            answer_entry_ids=answer_entry_ids,
            created_question_task_ids=[],
        )
    except Exception as error:
        decision = classify_apply_exception(error)
        run.status = decision.status
        run.completed_at = utcnow()
        _log_event(
            run,
            decision.status,
            {"message": str(error), "action_needed": decision.action_needed},
        )
        session.commit()
        return ApplyResult(
            application_run_id=run.id,
            status=run.status,
            answer_entry_ids=[],
            created_question_task_ids=[],
        )
