from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings, get_settings
from app.db.base import utcnow
from app.domains.accounts.models import Account
from app.domains.applications.models import ApplicationEvent, ApplicationRun
from app.domains.applications.redaction import redact_payload
from app.domains.jobs.models import ApplyTarget, Job
from app.domains.questions.fingerprints import ApplyQuestion
from app.domains.questions.matching import ensure_question_task, resolve_questions
from app.integrations.linkedin.artifacts import persist_artifacts
from app.integrations.linkedin.blockers import LinkedInAutomationError, classify_linkedin_exception
from app.integrations.linkedin.session_store import ensure_profile_dir


@dataclass(slots=True)
class LinkedInApplyResult:
    application_run_id: int
    status: str
    answer_entry_ids: list[int]
    created_question_task_ids: list[int]


@dataclass(slots=True)
class LinkedInInspection:
    step: str
    questions: list[ApplyQuestion] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LinkedInSubmission:
    step: str
    submission_payload: dict[str, Any] = field(default_factory=dict)
    response_payload: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)


InspectFn = Callable[[ApplyTarget, Path], LinkedInInspection]
SubmitFn = Callable[[ApplyTarget, Path, dict[str, Any]], LinkedInSubmission]


def _log_event(run: ApplicationRun, event_type: str, payload: dict[str, Any]) -> None:
    run.events.append(ApplicationEvent(event_type=event_type, payload=payload))


def _select_linkedin_target(job: Job) -> ApplyTarget:
    preferred = next(
        (
            target
            for target in job.apply_targets
            if target.is_preferred and target.target_type == "linkedin_easy_apply"
        ),
        None,
    )
    if preferred:
        return preferred

    target = next(
        (item for item in job.apply_targets if item.target_type == "linkedin_easy_apply"),
        None,
    )
    if target:
        return target

    raise ValueError("Job does not have a LinkedIn Easy Apply target")


def _default_inspect(apply_target: ApplyTarget, profile_dir: Path) -> LinkedInInspection:
    raise LinkedInAutomationError(
        code="runner_not_configured",
        step="bootstrap",
        message="LinkedIn automation runner is not configured for this environment.",
        artifacts={"profile_dir": str(profile_dir), "target_url": apply_target.destination_url},
    )


def _default_submit(
    apply_target: ApplyTarget,
    profile_dir: Path,
    answers_by_key: dict[str, Any],
) -> LinkedInSubmission:
    raise LinkedInAutomationError(
        code="runner_not_configured",
        step="submit",
        message="LinkedIn automation runner is not configured for this environment.",
        artifacts={
            "profile_dir": str(profile_dir),
            "target_url": apply_target.destination_url,
            "answers": redact_payload(answers_by_key),
        },
    )


def execute_linkedin_application_run(
    session: Session,
    *,
    account: Account,
    job_id: int,
    inspect_flow: InspectFn | None = None,
    submit_flow: SubmitFn | None = None,
    settings: Settings | None = None,
) -> LinkedInApplyResult:
    job = session.scalar(
        select(Job)
        .where(Job.id == job_id, Job.account_id == account.id)
        .options(
            selectinload(Job.apply_targets),
            selectinload(Job.question_tasks),
        ),
    )
    if not job:
        raise ValueError("Job not found")

    apply_target = _select_linkedin_target(job)
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

    resolved_settings = settings or get_settings()
    profile_dir = ensure_profile_dir(account.id, "linkedin", settings=resolved_settings)
    inspector = inspect_flow or _default_inspect
    submitter = submit_flow or _default_submit

    try:
        inspection = inspector(apply_target, profile_dir)
        _log_event(
            run,
            "questions_fetched",
            {"question_count": len(inspection.questions), "step": inspection.step},
        )

        resolved_questions = resolve_questions(session, account.id, inspection.questions)
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
                    "step": inspection.step,
                },
            )
            session.commit()
            return LinkedInApplyResult(
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
        submission = submitter(apply_target, profile_dir, answers_by_key)
        run.status = "submitted"
        run.completed_at = utcnow()
        _log_event(
            run,
            "submitted",
            {
                "answer_entry_ids": answer_entry_ids,
                "step": submission.step,
                "submission_payload": redact_payload(submission.submission_payload),
                "submit_response": redact_payload(submission.response_payload),
            },
        )
        session.commit()
        return LinkedInApplyResult(
            application_run_id=run.id,
            status=run.status,
            answer_entry_ids=answer_entry_ids,
            created_question_task_ids=[],
        )
    except Exception as error:
        decision = classify_linkedin_exception(error)
        artifacts = persist_artifacts(
            run.id,
            getattr(error, "artifacts", {}),
            settings=resolved_settings,
        )
        run.status = decision.status
        run.completed_at = utcnow()
        _log_event(
            run,
            decision.status,
            {
                "blocker_type": decision.category,
                "step": decision.step,
                "message": decision.message,
                "code": decision.code,
                "artifacts": artifacts,
            },
        )
        session.commit()
        return LinkedInApplyResult(
            application_run_id=run.id,
            status=run.status,
            answer_entry_ids=[],
            created_question_task_ids=[],
        )
