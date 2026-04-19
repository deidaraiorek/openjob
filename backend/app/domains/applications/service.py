from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

import httpx

from app.db.base import utcnow
from app.domains.accounts.models import Account
from app.domains.application_accounts.service import (
    decrypt_secret,
    ensure_target_ready,
    find_application_account_for_target,
)
from app.domains.applications.driver_registry import resolve_driver
from app.domains.applications.models import ApplicationEvent, ApplicationRun
from app.domains.applications.redaction import redact_payload
from app.domains.applications.retry_policy import (
    ActionNeededApplyError,
    RetryableApplyError,
    TerminalApplyError,
    classify_apply_exception,
)
from app.domains.jobs.models import ApplyTarget, Job
from app.domains.logs.service import log_system_event
from app.domains.questions.matching import build_question_answer_map, ensure_question_task, resolve_questions
from app.integrations.ai_browser.apply import execute_ai_browser_run
from app.integrations.ashby import apply as ashby_apply
from app.integrations.greenhouse import apply as greenhouse_apply
from app.integrations.lever import apply as lever_apply
from app.integrations.linkedin.apply import execute_linkedin_application_run
from app.integrations.smartrecruiters import apply as smartrecruiters_apply


@dataclass(slots=True)
class ApplyResult:
    application_run_id: int
    status: str
    answer_entry_ids: list[int]
    created_question_task_ids: list[int]


FetchQuestionsFn = Callable[[ApplyTarget], Any]
SubmitFn = Callable[[ApplyTarget, dict[str, Any]], dict[str, Any]]


def _log_event(run: ApplicationRun, event_type: str, payload: dict[str, Any], session: Session | None = None) -> None:
    run.events.append(ApplicationEvent(event_type=event_type, payload=payload))
    if session is not None:
        log_system_event(
            session,
            event_type=event_type,
            source="application_run",
            payload={"run_id": run.id, "job_id": run.job_id, **payload},
            account_id=run.account_id,
        )


def _default_fetch_questions(apply_target: ApplyTarget):
    try:
        if apply_target.target_type == "greenhouse_apply":
            board_token = apply_target.metadata_json["board_token"]
            job_post_id = apply_target.metadata_json["job_post_id"]
            return greenhouse_apply.fetch_question_payload(board_token, job_post_id)
        if apply_target.target_type == "lever_apply":
            posting_id = apply_target.metadata_json["posting_id"]
            company_slug = apply_target.metadata_json.get("company_slug")
            return lever_apply.fetch_question_payload(posting_id, company_slug)
        if apply_target.target_type == "ashby_apply":
            job_posting_id = apply_target.metadata_json["job_posting_id"]
            return ashby_apply.fetch_question_payload(job_posting_id)
        if apply_target.target_type == "smartrecruiters_apply":
            posting_id = apply_target.metadata_json["posting_id"]
            return smartrecruiters_apply.fetch_question_payload(posting_id)
    except Exception as error:  # pragma: no cover - real network path
        raise _classify_api_error(error) from error
    raise TerminalApplyError(f"Unsupported apply target: {apply_target.target_type}")


def _default_submit(apply_target: ApplyTarget, payload: dict[str, Any]) -> dict[str, Any]:
    if apply_target.target_type == "greenhouse_apply":
        try:
            return greenhouse_apply.submit_application(
                board_token=apply_target.metadata_json["board_token"],
                job_post_id=apply_target.metadata_json["job_post_id"],
                submission_payload=payload,
            )
        except Exception as error:  # pragma: no cover - real network path
            raise _classify_api_error(error) from error
    if apply_target.target_type == "lever_apply":
        try:
            return lever_apply.submit_application(
                posting_id=apply_target.metadata_json["posting_id"],
                company_slug=apply_target.metadata_json.get("company_slug"),
                submission_payload=payload,
            )
        except Exception as error:  # pragma: no cover - real network path
            raise _classify_api_error(error) from error
    if apply_target.target_type == "ashby_apply":
        try:
            return ashby_apply.submit_application(
                job_posting_id=apply_target.metadata_json["job_posting_id"],
                submission_payload=payload,
            )
        except Exception as error:  # pragma: no cover - real network path
            raise _classify_api_error(error) from error
    if apply_target.target_type == "smartrecruiters_apply":
        try:
            return smartrecruiters_apply.submit_application(
                posting_id=apply_target.metadata_json["posting_id"],
                submission_payload=payload,
            )
        except Exception as error:  # pragma: no cover - real network path
            raise _classify_api_error(error) from error
    raise TerminalApplyError(f"Unsupported apply target: {apply_target.target_type}")


def _parse_questions(apply_target: ApplyTarget, payload: Any):
    if apply_target.target_type == "greenhouse_apply":
        return greenhouse_apply.parse_question_payload(payload)
    if apply_target.target_type == "lever_apply":
        return lever_apply.parse_question_payload(payload)
    if apply_target.target_type == "ashby_apply":
        return ashby_apply.parse_question_payload(payload)
    if apply_target.target_type == "smartrecruiters_apply":
        return smartrecruiters_apply.parse_question_payload(payload)
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
    if apply_target.target_type == "ashby_apply":
        return ashby_apply.build_submission_payload(questions, answers_by_key)
    if apply_target.target_type == "smartrecruiters_apply":
        return smartrecruiters_apply.build_submission_payload(questions, answers_by_key)
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
    ensure_target_ready(session, account_id=account.id, target=apply_target)
    driver = resolve_driver(apply_target)

    if driver.key == "linkedin_browser":
        return execute_linkedin_application_run(
            session,
            account=account,
            job_id=job.id,
        )

    if driver.key == "ai_browser":
        app_account = find_application_account_for_target(session, account_id=account.id, target=apply_target)
        credential = decrypt_secret(app_account.secret_ciphertext) if app_account else None
        ai_result = execute_ai_browser_run(
            session,
            account=account,
            job_id=job.id,
            credential=credential,
        )
        return ApplyResult(
            application_run_id=ai_result.application_run_id,
            status=ai_result.status,
            answer_entry_ids=ai_result.answer_entry_ids,
            created_question_task_ids=ai_result.created_question_task_ids,
        )

    return _execute_direct_api_application_run(
        session,
        account=account,
        job=job,
        apply_target=apply_target,
        fetch_questions=fetch_questions,
        submit_application=submit_application,
    )


def _execute_direct_api_application_run(
    session: Session,
    *,
    account: Account,
    job: Job,
    apply_target: ApplyTarget,
    fetch_questions: FetchQuestionsFn | None = None,
    submit_application: SubmitFn | None = None,
) -> ApplyResult:
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
        session,
    )

    fetcher = fetch_questions or _default_fetch_questions
    submitter = submit_application or _default_submit

    try:
        question_payload = fetcher(apply_target)
        questions = _parse_questions(apply_target, question_payload)
        _log_event(run, "questions_fetched", {"question_count": len(questions)}, session)

        resolved_questions = resolve_questions(session, account.id, questions)
        answer_entry_ids = [
            item.answer_entry.id
            for item in resolved_questions
            if item.answer_entry is not None
        ]

        unresolved = [item for item in resolved_questions if item.answer_entry is None]
        unresolved_required = [item for item in unresolved if item.question.required]
        task_ids = [
            ensure_question_task(
                session,
                account_id=account.id,
                job_id=job.id,
                application_run_id=run.id,
                resolved_question=item,
            ).id
            for item in unresolved
        ]
        if unresolved_required:
            run.status = "blocked_missing_answer"
            run.completed_at = utcnow()
            _log_event(
                run,
                "blocked_missing_answer",
                {
                    "question_task_ids": task_ids,
                    "question_answer_map": build_question_answer_map(resolved_questions),
                },
                session,
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
        job.status = "applied"
        _log_event(
            run,
            "submitted",
            {
                "answer_entry_ids": answer_entry_ids,
                "question_answer_map": build_question_answer_map(resolved_questions),
                "submission_payload": redacted_payload,
                "submit_response": redact_payload(submit_response),
            },
            session,
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
        if decision.status == "failed" and apply_target.destination_url:
            _log_event(
                run,
                "browser_fallback_attempted",
                {"reason": str(error), "target_type": apply_target.target_type},
                session,
            )
            session.flush()
            ai_result = execute_ai_browser_run(
                session,
                account=account,
                job_id=job.id,
                destination_url=apply_target.destination_url,
                run=run,
            )
            return ApplyResult(
                application_run_id=ai_result.application_run_id,
                status=ai_result.status,
                answer_entry_ids=ai_result.answer_entry_ids,
                created_question_task_ids=ai_result.created_question_task_ids,
            )
        run.status = decision.status
        run.completed_at = utcnow()
        _log_event(
            run,
            decision.status,
            {"message": str(error), "action_needed": decision.action_needed},
            session,
        )
        session.commit()
        return ApplyResult(
            application_run_id=run.id,
            status=run.status,
            answer_entry_ids=[],
            created_question_task_ids=[],
        )


def _classify_api_error(error: Exception) -> Exception:
    if isinstance(error, httpx.HTTPStatusError):
        status_code = error.response.status_code
        if 400 <= status_code < 500:
            return TerminalApplyError(str(error))
    return RetryableApplyError(str(error))
