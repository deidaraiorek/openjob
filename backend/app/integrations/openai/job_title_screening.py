from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError

from app.config import Settings, get_settings

MAX_TITLE_SCREENING_BATCH_SIZE = 50


@dataclass(slots=True)
class JobTitleScreeningItem:
    title: str
    decision: str
    summary: str


@dataclass(slots=True)
class JobTitleScreeningResult:
    items: list[JobTitleScreeningItem]
    source: str
    model_name: str | None
    failure_cause: str | None
    payload: dict[str, Any]


def _build_ai_client(settings: Settings) -> tuple[OpenAI | None, str | None]:
    if settings.groq_api_key:
        return (
            OpenAI(api_key=settings.groq_api_key,
                   base_url=settings.groq_base_url),
            settings.groq_title_screening_model or settings.groq_model,
        )
    if settings.openai_api_key:
        return (OpenAI(api_key=settings.openai_api_key), settings.openai_job_relevance_model)
    return None, None


def _extract_completion_text(response: Any) -> str:
    content = response.choices[0].message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        fragments: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("text"):
                fragments.append(item["text"])
        return "".join(fragments)
    return str(content)


def _normalize_screening_decision(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"pass", "reject"}:
        return normalized
    return "pass"


def _normalize_text(value: str) -> str:
    return " ".join(value.lower().replace("-", " ").split())


def _default_summary_for_decision(decision: str) -> str:
    if decision == "pass":
        return "The title appears aligned with the target role family and level."
    if decision == "reject":
        return "The title appears outside the intended role family or level."
    return "The title appears aligned with the target role family and level."


def _sanitize_summary(*, title: str, decision: str, summary: Any) -> str:
    raw_summary = str(summary or "").strip()
    if not raw_summary:
        return _default_summary_for_decision(decision)
    normalized_summary = _normalize_text(raw_summary)
    normalized_title = _normalize_text(title)
    if normalized_summary == normalized_title or normalized_summary in normalized_title:
        return _default_summary_for_decision(decision)
    return raw_summary


def _fallback_result(
    titles: list[str],
    summary: str,
    *,
    failure_cause: str,
    payload: dict[str, Any] | None = None,
) -> JobTitleScreeningResult:
    return JobTitleScreeningResult(
        items=[JobTitleScreeningItem(
            title=title, decision="pass", summary=summary) for title in titles],
        source="system_fallback",
        model_name=None,
        failure_cause=failure_cause,
        payload=payload or {},
    )


def _classify_batch_with_ai(
    client: OpenAI,
    model: str,
    *,
    role_prompt: str,
    titles: list[str],
) -> JobTitleScreeningResult:
    response = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "You are screening job titles for a personal job assistant. "
                    "Given a user's desired role and a batch of job titles, classify each title as pass or reject. "
                    "Use pass when the title is plausibly in scope. "
                    "When in doubt, choose pass so the job can continue to deeper review. "
                    "Bias toward pass when the core role family aligns with the user's intent, even if the title wording is not an exact match. "
                    "Treat common wording variants, near-equivalents, and alternate phrasings within the same role family as in scope by default when they imply the same kind of work. "
                    "Treat specialization, team, platform, domain, technology, or focus-area modifiers as compatible by default unless they clearly imply a materially different function. "
                    "Treat neighboring early-career indicators and adjacent entry-level signals as compatible by default unless the title clearly implies a materially different seniority band. "
                    "Use reject only when the title is clearly out of scope or clearly too senior. "
                    "Write a concise summary that explains the classification reason in plain language. Do not simply repeat the title or company name. "
                    "Return JSON with a single key 'results' containing objects with keys title_index, decision, and summary. "
                    "Do not omit any title_index. Copy the exact title_index integer from the input."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "role_profile_prompt": role_prompt,
                        "titles": [
                            {"title_index": index, "title": title}
                            for index, title in enumerate(titles)
                        ],
                    }
                ),
            },
        ],
    )

    payload = json.loads(_extract_completion_text(response))
    raw_items = payload.get("results", [])
    if not isinstance(raw_items, list):
        raise TypeError("results must be a list")

    items_by_index: dict[int, JobTitleScreeningItem] = {}
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            raise TypeError("result item must be an object")
        title_index = raw_item.get("title_index")
        if not isinstance(title_index, int) or title_index < 0 or title_index >= len(titles):
            raise ValueError("result item missing a valid title_index")
        decision = _normalize_screening_decision(raw_item.get("decision"))
        title = titles[title_index]
        items_by_index[title_index] = JobTitleScreeningItem(
            title=title,
            decision=decision,
            summary=_sanitize_summary(
                title=title,
                decision=decision,
                summary=raw_item.get("summary"),
            ),
        )

    items: list[JobTitleScreeningItem] = []
    for index, title in enumerate(titles):
        items.append(
            items_by_index.get(
                index,
                JobTitleScreeningItem(
                    title=title,
                    decision="pass",
                    summary="Title screening did not return a result for this title, so it will continue to deeper review.",
                ),
            )
        )

    return JobTitleScreeningResult(
        items=items,
        source="ai",
        model_name=model,
        failure_cause=None,
        payload=payload,
    )


def classify_job_titles(
    role_prompt: str | None,
    titles: list[str],
    *,
    settings: Settings | None = None,
    client: OpenAI | None = None,
) -> JobTitleScreeningResult:
    normalized_titles = [title for title in titles if isinstance(
        title, str) and title.strip()]
    if not normalized_titles:
        return JobTitleScreeningResult(
            items=[],
            source="system_fallback",
            model_name=None,
            failure_cause=None,
            payload={},
        )
    if not role_prompt or not role_prompt.strip():
        return JobTitleScreeningResult(
            items=[
                JobTitleScreeningItem(
                    title=title,
                    decision="pass",
                    summary="No role profile configured, so the title stays visible by default.",
                )
                for title in normalized_titles
            ],
            source="system_fallback",
            model_name=None,
            failure_cause=None,
            payload={},
        )

    resolved_settings = settings or get_settings()
    configured_client, configured_model = _build_ai_client(resolved_settings)
    resolved_client = client or configured_client
    if resolved_client is None or not configured_model:
        return _fallback_result(
            normalized_titles,
            "AI title screening is unavailable because the provider is not configured.",
            failure_cause="config_missing",
        )

    retry_attempts = max(1, getattr(
        resolved_settings, "relevance_retry_attempts", 2))
    retry_delay_seconds = max(
        0.05,
        float(getattr(resolved_settings, "relevance_retry_base_delay_seconds", 0.5)),
    )

    batches = [
        normalized_titles[index: index + MAX_TITLE_SCREENING_BATCH_SIZE]
        for index in range(0, len(normalized_titles), MAX_TITLE_SCREENING_BATCH_SIZE)
    ]
    aggregated_items: list[JobTitleScreeningItem] = []
    aggregated_payloads: list[dict[str, Any]] = []
    used_fallback = False
    failure_causes: list[str] = []

    for batch in batches:
        batch_result: JobTitleScreeningResult | None = None
        for attempt in range(retry_attempts):
            try:
                batch_result = _classify_batch_with_ai(
                    resolved_client,
                    configured_model,
                    role_prompt=role_prompt,
                    titles=batch,
                )
                break
            except RateLimitError as error:
                if attempt < retry_attempts - 1:
                    time.sleep(retry_delay_seconds * (2**attempt))
                    continue
                batch_result = _fallback_result(
                    batch,
                    "AI title screening was rate-limited, so these titles need review.",
                    failure_cause="provider_rate_limited",
                    payload={"error_type": type(error).__name__},
                )
                break
            except (APITimeoutError, APIConnectionError) as error:
                if attempt < retry_attempts - 1:
                    time.sleep(retry_delay_seconds * (2**attempt))
                    continue
                batch_result = _fallback_result(
                    batch,
                    "AI title screening timed out, so these titles need review.",
                    failure_cause="provider_timeout",
                    payload={"error_type": type(error).__name__},
                )
                break
            except APIStatusError as error:
                if error.status_code == 429 and attempt < retry_attempts - 1:
                    time.sleep(retry_delay_seconds * (2**attempt))
                    continue
                batch_result = _fallback_result(
                    batch,
                    "AI title screening is temporarily unavailable, so these titles need review.",
                    failure_cause="provider_unavailable",
                    payload={"error_type": type(
                        error).__name__, "status_code": error.status_code},
                )
                break
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
                batch_result = _fallback_result(
                    batch,
                    "AI title screening returned an invalid response, so these titles need review.",
                    failure_cause="provider_response_invalid",
                    payload={"error_type": type(error).__name__},
                )
                break
            except Exception as error:
                batch_result = _fallback_result(
                    batch,
                    "AI title screening failed unexpectedly, so these titles need review.",
                    failure_cause="provider_unavailable",
                    payload={"error_type": type(error).__name__},
                )
                break

        if batch_result is None:
            batch_result = _fallback_result(
                batch,
                "AI title screening did not complete, so these titles need review.",
                failure_cause="provider_unavailable",
            )
        if batch_result.source != "ai":
            used_fallback = True
        if batch_result.failure_cause:
            failure_causes.append(batch_result.failure_cause)
        aggregated_items.extend(batch_result.items)
        aggregated_payloads.append(batch_result.payload)

    return JobTitleScreeningResult(
        items=aggregated_items,
        source="system_fallback" if used_fallback else "ai",
        model_name=configured_model,
        failure_cause=failure_causes[0] if failure_causes else None,
        payload={"batches": aggregated_payloads},
    )
