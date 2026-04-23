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
from app.domains.questions.matching import build_question_answer_map, ensure_question_task, resolve_questions
from app.domains.logs.service import log_system_event
from app.integrations.ai_browser.blockers import AIBrowserBlocker, classify_ai_browser_exception
from app.integrations.dom_scraper.ats_detect import is_supported as ats_is_supported
from app.integrations.dom_scraper.filler import DOMFillError, FillResult, fill_and_submit
from app.integrations.linkedin.artifacts import persist_artifacts
from app.integrations.linkedin.session_store import ensure_profile_dir

_DOM_STRIP_JS = """
() => {
    const selectors = [
        'nav', 'aside',
        'script', 'style', 'noscript',
        '[role="banner"]', '[role="navigation"]', '[role="contentinfo"]',
        '[aria-hidden="true"]',
        '.cookie-banner', '.cookie-notice', '#cookie-banner',
        '.ad', '.ads', '.advertisement',
        '.sidebar', '#sidebar',
        '.social-share', '.share-buttons',
    ];
    for (const sel of selectors) {
        document.querySelectorAll(sel).forEach(el => el.remove());
    }
}
"""


class ExtractedField(BaseModel):
    label: str
    field_type: str
    required: bool
    options: list[str] = Field(default_factory=list)
    placeholder: str | None = None


class ApplyOutput(BaseModel):
    submitted: bool
    missing_fields: list[ExtractedField] = Field(default_factory=list)


@dataclass(slots=True)
class AIBrowserResult:
    application_run_id: int
    status: str
    answer_entry_ids: list[int]
    created_question_task_ids: list[int]


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


def _build_llm(settings: Settings):
    from browser_use.llm.openai.chat import ChatOpenAI
    if settings.groq_api_key:
        return ChatOpenAI(
            model=settings.groq_browser_model,
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


_OPTIONAL_URL_FIELD_KEYWORDS = {
    "linkedin", "twitter", "github", "portfolio", "website", "url", "blog", "other link"}


def _build_apply_task(url: str, answers_by_key: dict[str, Any], credential: str | None) -> str:
    answers_json = json.dumps(answers_by_key, indent=2)
    return (
        f"Navigate to this job application page: {url}\n\n"
        "Your task is to fill in and submit the job application form.\n\n"
        f"You have these answers available:\n{answers_json}\n\n"
        "INSTRUCTIONS:\n"
        "1. Fill every field you have an answer for, matching by label or purpose.\n"
        "2. For multi-step forms, complete each step and click Next/Continue to advance.\n"
        "3. Do NOT invent or guess values for fields you have no answer for.\n"
        "4. If you encounter a required field with no matching answer, STOP — do not submit.\n"
        "   Instead, record all such unanswered required fields in missing_fields.\n"
        "5. If you encounter a CAPTCHA, stop and report it.\n"
        "6. If all required fields are answered, click Submit and set submitted=true.\n\n"
        "Return structured output with:\n"
        "- submitted: true if the form was successfully submitted, false if you had to stop\n"
        "- missing_fields: list of required fields you could not answer (empty if submitted)\n"
        "  For each missing field include: label, field_type, required=true, options (if select/radio/checkbox), placeholder"
        + _credential_block(credential)
    )


def _run_sync(coro) -> Any:
    return asyncio.run(coro)


async def _strip_dom(agent) -> None:
    try:
        page = await agent.browser_session.get_current_page()
        if page:
            await page.evaluate(_DOM_STRIP_JS)
    except Exception:
        pass


def _run_apply_agent(
    url: str,
    answers_by_key: dict[str, Any],
    credential: str | None,
    settings: Settings,
) -> ApplyOutput:
    from browser_use import Agent, Browser

    llm = _build_llm(settings)
    task = _build_apply_task(url, answers_by_key, credential)

    async def _run():
        browser = Browser(headless=settings.playwright_headless)
        agent = Agent(
            task=task,
            llm=llm,
            browser=browser,
            output_model_schema=ApplyOutput,
        )
        return await agent.run(max_steps=100, on_step_start=_strip_dom)

    history = _run_sync(_run())

    raw = history.final_result()
    if not raw:
        structured_fn = getattr(history, "structured_output", None)
        raw = structured_fn() if callable(structured_fn) else None

    if not raw:
        raise AIBrowserBlocker(
            code="no_form_found",
            step="apply",
            message="AI browser agent returned no output.",
        )

    try:
        return ApplyOutput.model_validate_json(raw) if isinstance(raw, str) else ApplyOutput.model_validate(raw)
    except Exception:
        raise AIBrowserBlocker(
            code="no_form_found",
            step="apply",
            message=f"AI browser agent returned unparseable output: {raw!r}",
        )


def _parse_extracted_fields(fields: list[ExtractedField]) -> list[ApplyQuestion]:
    questions = []
    for q in fields:
        label_lower = q.label.lower()
        is_optional_url = any(kw in label_lower for kw in _OPTIONAL_URL_FIELD_KEYWORDS)
        is_eeo_voluntary = any(kw in label_lower for kw in {
            "gender", "race", "ethnicity", "veteran", "disability", "eeo", "diversity"})
        is_substantive_choice = q.field_type in {"radio", "select", "checkbox"} and len(q.options) > 0
        required = q.required or (is_substantive_choice and not is_optional_url and not is_eeo_voluntary)
        questions.append(ApplyQuestion(
            key=q.label.lower().replace(" ", "_")[:64],
            prompt_text=q.label,
            field_type=q.field_type,
            required=required,
            option_labels=q.options,
            placeholder_text=q.placeholder or None,
        ))
    return questions


def _run_dom_apply(url: str, answers_by_key: dict[str, Any], credential: str | None, settings: Settings) -> ApplyOutput:
    from playwright.sync_api import sync_playwright
    from app.integrations.browser_context import _CHROMIUM_ARGS, _NAVIGATOR_WEBDRIVER_SCRIPT

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=settings.playwright_headless, args=_CHROMIUM_ARGS)
        context = browser.new_context()
        context.add_init_script(_NAVIGATOR_WEBDRIVER_SCRIPT)
        context.set_default_timeout(settings.playwright_timeout_ms)
        page = context.new_page()

        try:
            page.goto(url, wait_until="networkidle")

            if credential:
                pass

            result = fill_and_submit(page, answers_by_key)

            if result.submitted:
                return ApplyOutput(submitted=True)

            return ApplyOutput(
                submitted=False,
                missing_fields=[
                    ExtractedField(
                        label=f.label,
                        field_type=f.field_type,
                        required=f.required,
                        options=f.options,
                        placeholder=f.placeholder,
                    )
                    for f in result.missing_fields
                ],
            )
        finally:
            browser.close()


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
            session,
        )

    ensure_profile_dir(account.id, "ai_browser", settings=resolved_settings)

    try:
        answers_by_key = _load_all_answers(session, account.id)

        if ats_is_supported(resolved_url):
            try:
                result = _run_dom_apply(resolved_url, answers_by_key, credential, resolved_settings)
                _log_event(run, "dom_apply_attempted", {"driver": "dom_scraper", "url": resolved_url}, session)
            except Exception:
                result = _run_apply_agent(resolved_url, answers_by_key, credential, resolved_settings)
                _log_event(run, "dom_apply_fallback", {"driver": "ai_browser", "url": resolved_url}, session)
        else:
            result = _run_apply_agent(resolved_url, answers_by_key, credential, resolved_settings)

        if result.submitted:
            run.status = "submitted"
            run.completed_at = utcnow()
            job.status = "applied"
            _log_event(
                run,
                "submitted",
                {"driver": "ai_browser", "submit_result": redact_payload({"submitted": True})},
                session,
            )
            session.commit()
            return AIBrowserResult(
                application_run_id=run.id,
                status=run.status,
                answer_entry_ids=[],
                created_question_task_ids=[],
            )

        missing = _parse_extracted_fields(result.missing_fields)
        _log_event(run, "questions_fetched", {"question_count": len(missing), "driver": "ai_browser"}, session)

        resolved_questions = resolve_questions(session, account.id, missing)
        answer_entry_ids = [
            item.answer_entry.id for item in resolved_questions if item.answer_entry is not None
        ]
        task_ids = [
            ensure_question_task(
                session,
                account_id=account.id,
                job_id=job.id,
                application_run_id=run.id,
                resolved_question=item,
            ).id
            for item in resolved_questions
            if item.answer_entry is None
        ]

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
        return AIBrowserResult(
            application_run_id=run.id,
            status=run.status,
            answer_entry_ids=answer_entry_ids,
            created_question_task_ids=task_ids,
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
            session,
        )
        session.commit()
        return AIBrowserResult(
            application_run_id=run.id,
            status=run.status,
            answer_entry_ids=[],
            created_question_task_ids=[],
        )


def _load_all_answers(session: Session, account_id: int) -> dict[str, Any]:
    from app.domains.questions.models import AnswerEntry, QuestionTemplate
    rows = session.execute(
        select(QuestionTemplate.prompt_text, AnswerEntry)
        .join(AnswerEntry, AnswerEntry.question_template_id == QuestionTemplate.id)
        .where(
            QuestionTemplate.account_id == account_id,
            AnswerEntry.account_id == account_id,
        )
        .order_by(AnswerEntry.created_at.desc())
    ).all()

    seen: set[str] = set()
    answers: dict[str, Any] = {}
    for prompt_text, entry in rows:
        if prompt_text in seen:
            continue
        seen.add(prompt_text)
        payload = entry.answer_payload or {}
        if "values" in payload:
            answers[prompt_text] = payload["values"]
        elif "value" in payload:
            answers[prompt_text] = payload["value"]
        elif entry.answer_text:
            answers[prompt_text] = entry.answer_text
    return answers
