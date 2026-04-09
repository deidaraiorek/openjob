from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError

from app.config import Settings, get_settings
from app.domains.jobs.relevance_policy import build_role_context_for_screening


TITLE_SCREENING_SCHEMA = {
    "name": "job_title_screening_batch",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "title_index": {"type": "integer"},
                        "decision": {"type": "string", "enum": ["pass", "reject"]},
                        "summary": {"type": "string"},
                        "decision_rationale_type": {
                            "type": "string",
                            "enum": [
                                "family_match",
                                "specialization_only",
                                "clear_family_mismatch",
                                "clear_seniority_mismatch",
                                "adjacent_level_variant",
                                "ambiguous_but_passed",
                            ],
                        },
                        "role_family_alignment": {
                            "type": "string",
                            "enum": ["same_family", "different_family", "uncertain"],
                        },
                        "seniority_alignment": {
                            "type": "string",
                            "enum": ["compatible", "incompatible", "uncertain"],
                        },
                    },
                    "required": [
                        "title_index",
                        "decision",
                        "summary",
                        "decision_rationale_type",
                        "role_family_alignment",
                        "seniority_alignment",
                    ],
                },
            }
        },
        "required": ["results"],
    },
}

TITLE_SCREENING_REPAIR_SCHEMA = {
    "name": "job_title_screening_repair",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "decision": {"type": "string", "enum": ["pass", "reject"]},
            "summary": {"type": "string"},
            "decision_rationale_type": {
                "type": "string",
                "enum": [
                    "family_match",
                    "specialization_only",
                    "clear_family_mismatch",
                    "clear_seniority_mismatch",
                    "adjacent_level_variant",
                    "ambiguous_but_passed",
                ],
            },
            "role_family_alignment": {
                "type": "string",
                "enum": ["same_family", "different_family", "uncertain"],
            },
            "seniority_alignment": {
                "type": "string",
                "enum": ["compatible", "incompatible", "uncertain"],
            },
        },
        "required": [
            "decision",
            "summary",
            "decision_rationale_type",
            "role_family_alignment",
            "seniority_alignment",
        ],
    },
}


def _json_schema_response_format(schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema["name"],
            "schema": schema["schema"],
            # Groq Scout supports best-effort json_schema but not strict constrained decoding.
            "strict": False,
        },
    }


@dataclass(slots=True)
class JobTitleScreeningItem:
    title: str
    decision: str
    summary: str
    decision_rationale_type: str | None = None
    source: str = "ai"
    model_name: str | None = None
    failure_cause: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


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


def _normalize_rationale_type(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    if normalized in {
        "family_match",
        "specialization_only",
        "clear_family_mismatch",
        "clear_seniority_mismatch",
        "adjacent_level_variant",
        "ambiguous_but_passed",
    }:
        return normalized
    return "ambiguous_but_passed"


def _normalize_role_family_alignment(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"same_family", "different_family", "uncertain"}:
        return normalized
    if normalized == "adjacent_family":
        return "different_family"
    return None


def _normalize_seniority_alignment(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"compatible", "incompatible", "uncertain"}:
        return normalized
    if normalized in {"same_band", "adjacent_or_same", "more_junior"}:
        return "compatible"
    if normalized == "more_senior":
        return "incompatible"
    return None


def _normalize_modifier_impact(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"none", "specialization_only", "material_scope_change", "uncertain"}:
        return normalized
    return None


def _normalize_contradiction_strength(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"none", "weak", "moderate", "strong"}:
        return normalized
    return None


def _structured_fields_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "decision_rationale_type": _normalize_rationale_type(payload.get("decision_rationale_type")),
        "role_family_alignment": _normalize_role_family_alignment(payload.get("role_family_alignment")),
        "seniority_alignment": _normalize_seniority_alignment(payload.get("seniority_alignment")),
        "modifier_impact": _normalize_modifier_impact(payload.get("modifier_impact")),
        "contradiction_strength": _normalize_contradiction_strength(payload.get("contradiction_strength")),
    }


def _title_screening_supported(payload: dict[str, Any]) -> bool:
    structured = _structured_fields_payload(payload)
    return all(value is not None for value in structured.values())


def _title_screening_safe_reject(payload: dict[str, Any]) -> bool:
    family = _normalize_role_family_alignment(payload.get("role_family_alignment"))
    seniority = _normalize_seniority_alignment(payload.get("seniority_alignment"))
    rationale = _normalize_rationale_type(payload.get("decision_rationale_type"))

    if None in {family, seniority, rationale}:
        return False
    if family == "different_family" and rationale == "clear_family_mismatch":
        return True
    return seniority == "incompatible" and rationale == "clear_seniority_mismatch"


def _title_screening_inconsistent(*, decision: str, payload: dict[str, Any]) -> bool:
    family = _normalize_role_family_alignment(payload.get("role_family_alignment"))
    seniority = _normalize_seniority_alignment(payload.get("seniority_alignment"))
    rationale = _normalize_rationale_type(payload.get("decision_rationale_type"))

    if None in {family, seniority, rationale}:
        return True
    if decision == "pass" and family == "different_family" and rationale == "clear_family_mismatch":
        return True
    if decision == "pass" and seniority == "incompatible" and rationale == "clear_seniority_mismatch":
        return True
    return (
        decision == "reject"
        and family == "same_family"
        and seniority == "compatible"
        and rationale in {"family_match", "specialization_only", "adjacent_level_variant"}
    )


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
            title=title,
            decision="pass",
            summary=summary,
            decision_rationale_type="ambiguous_but_passed",
            source="system_fallback",
            failure_cause=failure_cause,
            payload={},
        ) for title in titles],
        source="system_fallback",
        model_name=None,
        failure_cause=failure_cause,
        payload=payload or {},
    )


def _repair_item_with_ai(
    client: OpenAI,
    model: str,
    *,
    role_prompt: str,
    title: str,
    decision_policy: dict[str, str | bool],
    derived_profile_hints: dict[str, str | bool],
    original_payload: dict[str, Any],
) -> JobTitleScreeningItem:
    response = client.chat.completions.create(
        model=model,
        response_format=_json_schema_response_format(TITLE_SCREENING_REPAIR_SCHEMA),
        messages=[
            {
                "role": "system",
                "content": (
                    "Repair a title-screening decision so the structured fields and final decision agree. "
                    "This is a high-recall safety gate: only keep reject when title alone safely excludes the job from deeper review. "
                    "Return JSON with keys decision, summary, decision_rationale_type, role_family_alignment, seniority_alignment, modifier_impact, and contradiction_strength. "
                    "Valid decisions are pass or reject."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "role_profile_prompt": role_prompt,
                        "derived_profile_hints": derived_profile_hints,
                        "decision_policy": decision_policy,
                        "title": title,
                        "previous_result": original_payload,
                        "instructions": [
                            "Title screening should only reject when title alone safely excludes the job from deeper review.",
                            "Specialization within the same family should remain same_family.",
                            "Titles that narrow the work by platform, application layer, delivery surface, or implementation specialty should remain same_family when the underlying discipline is the same.",
                            "Different disciplines are different_family even if they are in the same industry or engineering organization.",
                            "If the title is same_family, or family is uncertain, and seniority is compatible or uncertain, choose pass.",
                            "If the title is different_family with a material scope change and clear contradiction, choose reject.",
                        ],
                    }
                ),
            },
        ],
    )
    payload = json.loads(_extract_completion_text(response))
    decision = _normalize_screening_decision(payload.get("decision"))
    if _title_screening_inconsistent(decision=decision, payload=payload):
        return JobTitleScreeningItem(
            title=title,
            decision="pass",
            summary="Title screening repair produced an inconsistent result, so the title passes to deeper review.",
            decision_rationale_type="ambiguous_but_passed",
            source="ai",
            model_name=model,
            failure_cause=None,
            payload=_structured_fields_payload(payload),
        )
    return JobTitleScreeningItem(
        title=title,
        decision=decision,
        summary=_sanitize_summary(title=title, decision=decision, summary=payload.get("summary")),
        decision_rationale_type=_normalize_rationale_type(payload.get("decision_rationale_type")),
        source="ai",
        model_name=model,
        failure_cause=None,
        payload=_structured_fields_payload(payload),
    )


def _parse_ratelimit_reset_seconds(headers: Any) -> float | None:
    remaining = headers.get("x-ratelimit-remaining-tokens")
    reset_str = headers.get("x-ratelimit-reset-tokens")
    if remaining is None or reset_str is None:
        return None
    try:
        remaining_tokens = int(remaining)
    except (ValueError, TypeError):
        return None
    if remaining_tokens > 5000:
        return None
    reset_str = str(reset_str).strip().lower()
    total_seconds = 0.0
    for value, unit in re.findall(r"(\d+(?:\.\d+)?)(ms|s|m)", reset_str):
        v = float(value)
        if unit == "ms":
            total_seconds += v / 1000
        elif unit == "s":
            total_seconds += v
        elif unit == "m":
            total_seconds += v * 60
    return max(0.0, total_seconds) if total_seconds > 0 else None


def _classify_batch_with_ai(
    client: OpenAI,
    model: str,
    *,
    role_prompt: str,
    titles: list[str],
    decision_policy: dict[str, str | bool],
    derived_profile_hints: dict[str, str | bool],
) -> tuple[JobTitleScreeningResult, Any]:
    role_context = build_role_context_for_screening(role_prompt, derived_profile_hints)
    role_context_prefix = (role_context + " ") if role_context else ""
    raw = client.chat.completions.with_raw_response.create(
        model=model,
        response_format=_json_schema_response_format(TITLE_SCREENING_SCHEMA),
        messages=[
            {
                "role": "system",
                "content": (
                    f"{role_context_prefix} "
                    "High-recall title gate: pass unless the title alone is clear evidence the job is out of scope. "
                    "Pass: same role family (including specializations, platforms, tech modifiers), adjacent level variants, or anything ambiguous. "
                    "Reject: clearly different discipline, or clearly too senior — title must make this unambiguous without job description context. "
                    "Same industry or engineering org is not the same discipline. Different core function is a different family. "
                    "Structured fields must be consistent with your decision. "
                    "Do not omit any title_index."
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
    response = raw.parse()

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
        item_payload = _structured_fields_payload(raw_item)
        try:
            item = JobTitleScreeningItem(
                title=title,
                decision=decision,
                summary=_sanitize_summary(
                    title=title,
                    decision=decision,
                    summary=raw_item.get("summary"),
                ),
                decision_rationale_type=_normalize_rationale_type(raw_item.get("decision_rationale_type")),
                source="ai",
                model_name=model,
                failure_cause=None,
                payload=item_payload,
            )
            if _title_screening_inconsistent(decision=item.decision, payload=item.payload):
                item = _repair_item_with_ai(
                    client,
                    model,
                    role_prompt=role_prompt,
                    title=title,
                    decision_policy=decision_policy,
                    derived_profile_hints=derived_profile_hints,
                    original_payload=raw_item,
                )
            elif item.decision == "reject" and not _title_screening_safe_reject(item.payload):
                item = JobTitleScreeningItem(
                    title=title,
                    decision="pass",
                    summary="Title screening reject did not meet the safe-reject threshold, so the title passes to deeper review.",
                    decision_rationale_type="ambiguous_but_passed",
                    source="ai",
                    model_name=model,
                    failure_cause=None,
                    payload=item.payload,
                )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            item = JobTitleScreeningItem(
                title=title,
                decision="pass",
                summary="AI title screening returned an inconsistent result for this title, so it is pending a retry.",
                decision_rationale_type="ambiguous_but_passed",
                source="system_fallback",
                model_name=None,
                failure_cause="provider_response_invalid",
                payload={},
            )
        items_by_index[title_index] = item

    items: list[JobTitleScreeningItem] = []
    for index, title in enumerate(titles):
        items.append(
            items_by_index.get(
                index,
                JobTitleScreeningItem(
                    title=title,
                    decision="pass",
                    summary="Title screening did not return a result for this title, so it is pending a retry.",
                    decision_rationale_type="ambiguous_but_passed",
                    source="system_fallback",
                    model_name=None,
                    failure_cause="provider_response_invalid",
                    payload={},
                ),
            )
        )

    return JobTitleScreeningResult(
        items=items,
        source="ai",
        model_name=model,
        failure_cause=None,
        payload=payload,
    ), raw.headers


def classify_job_titles(
    role_prompt: str | None,
    titles: list[str],
    *,
    decision_policy: dict[str, str | bool] | None = None,
    derived_profile_hints: dict[str, str | bool] | None = None,
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
                    decision_rationale_type="ambiguous_but_passed",
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

    batch_size = max(1, resolved_settings.title_screening_batch_size)
    batches = [
        normalized_titles[index: index + batch_size]
        for index in range(0, len(normalized_titles), batch_size)
    ]
    aggregated_items: list[JobTitleScreeningItem] = []
    aggregated_payloads: list[dict[str, Any]] = []
    used_fallback = False
    failure_causes: list[str] = []

    for batch in batches:
        batch_result: JobTitleScreeningResult | None = None
        ratelimit_headers: Any = None
        for attempt in range(retry_attempts):
            try:
                batch_result, ratelimit_headers = _classify_batch_with_ai(
                    resolved_client,
                    configured_model,
                    role_prompt=role_prompt,
                    titles=batch,
                    decision_policy=decision_policy or {},
                    derived_profile_hints=derived_profile_hints or {},
                )
                break
            except RateLimitError as error:
                if attempt < retry_attempts - 1:
                    time.sleep(retry_delay_seconds * (2**attempt))
                    continue
                batch_result = _fallback_result(
                    batch,
                    "AI title screening was rate-limited, so these titles are pending a retry.",
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
                    "AI title screening timed out, so these titles are pending a retry.",
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
                    "AI title screening is temporarily unavailable, so these titles are pending a retry.",
                    failure_cause="provider_unavailable",
                    payload={"error_type": type(
                        error).__name__, "status_code": error.status_code},
                )
                break
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
                batch_result = _fallback_result(
                    batch,
                    "AI title screening returned an invalid response, so these titles are pending a retry.",
                    failure_cause="provider_response_invalid",
                    payload={"error_type": type(error).__name__},
                )
                break
            except Exception as error:
                batch_result = _fallback_result(
                    batch,
                    "AI title screening failed unexpectedly, so these titles are pending a retry.",
                    failure_cause="provider_unavailable",
                    payload={"error_type": type(error).__name__},
                )
                break

        if batch_result is None:
            batch_result = _fallback_result(
                batch,
                "AI title screening did not complete, so these titles are pending a retry.",
                failure_cause="provider_unavailable",
            )
        if batch_result.source != "ai":
            used_fallback = True
        if batch_result.failure_cause:
            failure_causes.append(batch_result.failure_cause)
        aggregated_items.extend(batch_result.items)
        aggregated_payloads.append(batch_result.payload)

        if ratelimit_headers is not None and len(aggregated_items) < len(normalized_titles):
            header_sleep = _parse_ratelimit_reset_seconds(ratelimit_headers)
            if header_sleep is not None:
                time.sleep(header_sleep)

    return JobTitleScreeningResult(
        items=aggregated_items,
        source="system_fallback" if used_fallback else "ai",
        model_name=configured_model,
        failure_cause=failure_causes[0] if failure_causes else None,
        payload={"batches": aggregated_payloads},
    )
