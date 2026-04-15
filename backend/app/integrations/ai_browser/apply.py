from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings, get_settings
from app.db.base import utcnow
from app.domains.accounts.models import Account
from app.domains.applications.models import ApplicationEvent, ApplicationRun
from app.domains.applications.redaction import redact_payload
from app.domains.applications.retry_policy import RetryableApplyError, TerminalApplyError, classify_apply_exception
from app.domains.jobs.models import ApplyTarget, Job
from app.domains.questions.fingerprints import ApplyQuestion
from app.domains.questions.matching import ensure_question_task, resolve_questions
from app.integrations.ai_browser.blockers import AIBrowserBlocker, classify_ai_browser_exception
from app.integrations.linkedin.artifacts import persist_artifacts
from app.integrations.linkedin.session_store import ensure_profile_dir


class ExtractedField(BaseModel):
    label: str
    field_type: str
    required: bool
    options: list[str] = Field(default_factory=list)


class InspectOutput(BaseModel):
    questions: list[ExtractedField]


@dataclass(slots=True)
class AIBrowserResult:
    application_run_id: int
    status: str
    answer_entry_ids: list[int]
    created_question_task_ids: list[int]


def _log_event(run: ApplicationRun, event_type: str, payload: dict[str, Any]) -> None:
    run.events.append(ApplicationEvent(event_type=event_type, payload=payload))


def _build_llm(settings: Settings):
    from browser_use.llm.openai.chat import ChatOpenAI
    if settings.groq_api_key:
        # Groq's API doesn't support OpenAI's json_schema response_format with strict mode.
        # We disable forced structured output and put the schema in the system prompt instead,
        # then parse the raw text response ourselves.
        return ChatOpenAI(
            model=settings.groq_model,
            api_key=settings.groq_api_key,
            base_url=settings.groq_base_url,
            dont_force_structured_output=True,
            add_schema_to_system_prompt=True,
        )
    if settings.openai_api_key:
        return ChatOpenAI(
            model="gpt-4o-mini",
            api_key=settings.openai_api_key,
        )
    raise AIBrowserBlocker(
        code="config_missing",
        step="setup",
        message="No LLM API key configured. Set GROQ_API_KEY or OPENAI_API_KEY.",
    )


def _credential_block(credential: str | None) -> str:
    if not credential:
        return ""
    return (
        "\n\nIf the page requires login before showing the application form, "
        f"use these credentials to log in: {credential}"
    )


_OPTIONAL_URL_FIELD_KEYWORDS = {"linkedin", "twitter", "github", "portfolio", "website", "url", "blog", "other link"}


def _build_inspect_task(url: str, credential: str | None) -> str:
    return (
        f"Navigate to this job application page: {url}\n\n"
        "Your task is to INSPECT the application form only — do NOT fill in or submit anything.\n\n"
        "Extract every visible form field from the application form. For each field, record:\n"
        "- label: the human-readable label or question text\n"
        "- field_type: one of 'text', 'textarea', 'select', 'checkbox', 'radio', 'file', 'email', 'tel'\n"
        "- required: true for ANY field that the applicant must answer to successfully submit — "
        "this includes fields marked with *, fields that are substantive questions (work authorization, "
        "location preferences, employment type, eligibility questions), and file uploads. "
        "Mark required: false ONLY for clearly optional fields like LinkedIn URL, GitHub URL, portfolio, "
        "Twitter, phone, current company, and EEO/diversity voluntary fields.\n"
        "- options: list of option labels for select/radio/checkbox fields, empty list otherwise\n\n"
        "If the form has multiple steps or pages, navigate through all steps to discover all fields "
        "but do NOT fill anything in.\n\n"
        "Return the complete list of fields as structured output."
        + _credential_block(credential)
    )


def _build_submit_task(url: str, answers_by_key: dict[str, Any], credential: str | None) -> str:
    answers_json = json.dumps(answers_by_key, indent=2)
    return (
        f"Navigate to this job application page: {url}\n\n"
        "Your task is to fill in and submit the job application form using ONLY the answers provided below.\n\n"
        f"Available answers:\n{answers_json}\n\n"
        "IMPORTANT RULES:\n"
        "- Do NOT fill any field for which you do not have a provided answer\n"
        "- Do NOT invent, guess, or hallucinate any values\n"
        "- Match each answer to the form field by its label or purpose\n"
        "- For multi-step forms, complete each step in order and click Next/Continue to advance\n"
        "- After filling all available fields, click the final Submit button\n"
        "- If you encounter a CAPTCHA, stop and report it\n\n"
        "Complete the submission."
        + _credential_block(credential)
    )


def _run_sync(coro) -> Any:
    return asyncio.run(coro)


def _run_inspect_agent(url: str, credential: str | None, settings: Settings) -> list[ApplyQuestion]:
    from browser_use import Agent, Browser

    llm = _build_llm(settings)
    task = _build_inspect_task(url, credential)

    async def _run():
        browser = Browser(headless=settings.playwright_headless)
        agent = Agent(
            task=task,
            llm=llm,
            browser=browser,
            output_model_schema=InspectOutput,
        )
        return await agent.run(max_steps=50)

    history = _run_sync(_run())

    raw = history.final_result()
    if not raw:
        structured = history.structured_output() if hasattr(history, "structured_output") else None
        if not structured:
            raise AIBrowserBlocker(
                code="no_form_found",
                step="inspect",
                message="AI browser agent could not find any form fields on the page.",
            )
        raw = structured

    try:
        output = InspectOutput.model_validate_json(raw) if isinstance(raw, str) else InspectOutput.model_validate(raw)
    except Exception:
        raise AIBrowserBlocker(
            code="no_form_found",
            step="inspect",
            message=f"AI browser agent returned unparseable output: {raw!r}",
        )

    if not output.questions:
        raise AIBrowserBlocker(
            code="no_form_found",
            step="inspect",
            message="AI browser agent found zero form fields.",
        )

    questions = []
    for q in output.questions:
        label_lower = q.label.lower()
        is_optional_url = any(kw in label_lower for kw in _OPTIONAL_URL_FIELD_KEYWORDS)
        is_eeo_voluntary = any(kw in label_lower for kw in {"gender", "race", "ethnicity", "veteran", "disability", "eeo", "diversity"})
        is_substantive_choice = q.field_type in {"radio", "select", "checkbox"} and len(q.options) > 0
        required = q.required or (is_substantive_choice and not is_optional_url and not is_eeo_voluntary)
        questions.append(ApplyQuestion(
            key=q.label.lower().replace(" ", "_")[:64],
            prompt_text=q.label,
            field_type=q.field_type,
            required=required,
            option_labels=q.options,
        ))
    return questions


def _run_submit_agent(
    url: str,
    answers_by_key: dict[str, Any],
    credential: str | None,
    settings: Settings,
) -> dict[str, Any]:
    from browser_use import Agent, Browser

    llm = _build_llm(settings)
    task = _build_submit_task(url, answers_by_key, credential)

    async def _run():
        browser = Browser(headless=settings.playwright_headless)
        agent = Agent(
            task=task,
            llm=llm,
            browser=browser,
        )
        return await agent.run(max_steps=100)

    history = _run_sync(_run())

    return {"action_count": len(history.action_names()), "final_result": history.final_result()}


def _select_target(job: Job, destination_url: str | None) -> ApplyTarget:
    if destination_url:
        for t in job.apply_targets:
            if t.destination_url == destination_url:
                return t
        raise TerminalApplyError(f"No apply target found with destination URL: {destination_url}")
    preferred = next((t for t in job.apply_targets if t.is_preferred), None)
    if preferred:
        return preferred
    if job.apply_targets:
        return job.apply_targets[0]
    raise TerminalApplyError("Job does not have an apply target")


def execute_ai_browser_run(
    session: Session,
    *,
    account: Account,
    job_id: int,
    credential: str | None = None,
    destination_url: str | None = None,
    run: ApplicationRun | None = None,
    settings: Settings | None = None,
) -> AIBrowserResult:
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

    apply_target = _select_target(job, destination_url)
    resolved_url = destination_url or apply_target.destination_url
    resolved_settings = settings or get_settings()

    if run is None:
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
            {"apply_target_id": apply_target.id, "target_type": apply_target.target_type, "driver": "ai_browser"},
        )

    profile_dir = ensure_profile_dir(account.id, "ai_browser", settings=resolved_settings)

    try:
        questions = _run_inspect_agent(resolved_url, credential, resolved_settings)
        _log_event(run, "questions_fetched", {"question_count": len(questions), "driver": "ai_browser"})

        resolved_questions = resolve_questions(session, account.id, questions)
        answer_entry_ids = [
            item.answer_entry.id for item in resolved_questions if item.answer_entry is not None
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
            return AIBrowserResult(
                application_run_id=run.id,
                status=run.status,
                answer_entry_ids=answer_entry_ids,
                created_question_task_ids=task_ids,
            )

        answers_by_key = {
            item.question.prompt_text: item.answer_value
            for item in resolved_questions
            if item.answer_entry is not None
        }

        submit_result = _run_submit_agent(resolved_url, answers_by_key, credential, resolved_settings)
        run.status = "submitted"
        run.completed_at = utcnow()
        _log_event(
            run,
            "submitted",
            {
                "answer_entry_ids": answer_entry_ids,
                "driver": "ai_browser",
                "submit_result": redact_payload(submit_result),
            },
        )
        session.commit()
        return AIBrowserResult(
            application_run_id=run.id,
            status=run.status,
            answer_entry_ids=answer_entry_ids,
            created_question_task_ids=[],
        )

    except Exception as error:
        classified = classify_ai_browser_exception(error)
        artifacts = persist_artifacts(
            run.id,
            getattr(error, "artifacts", {}),
            settings=resolved_settings,
        )
        is_terminal = isinstance(classified, TerminalApplyError)
        run.status = "failed" if is_terminal else "retry_scheduled"
        run.completed_at = utcnow()
        _log_event(
            run,
            run.status,
            {
                "driver": "ai_browser",
                "code": getattr(error, "code", None),
                "step": getattr(error, "step", None),
                "message": str(error),
                "artifacts": artifacts,
            },
        )
        session.commit()
        return AIBrowserResult(
            application_run_id=run.id,
            status=run.status,
            answer_entry_ids=[],
            created_question_task_ids=[],
        )
