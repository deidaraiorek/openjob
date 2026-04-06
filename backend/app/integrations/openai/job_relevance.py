from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError

from app.config import Settings, get_settings
from app.domains.role_profiles.models import RoleProfile


@dataclass(slots=True)
class JobRelevanceResult:
    decision: str
    score: float | None
    summary: str
    matched_signals: list[str]
    concerns: list[str]
    source: str
    model_name: str | None
    failure_cause: str | None
    payload: dict[str, Any]


def _normalize_list(values: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        collapsed = " ".join(value.strip().split())
        if not collapsed:
            continue
        lowered = collapsed.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(collapsed)
    return normalized


def _build_ai_client(settings: Settings) -> tuple[OpenAI | None, str | None]:
    if settings.groq_api_key:
        return (
            OpenAI(api_key=settings.groq_api_key, base_url=settings.groq_base_url),
            settings.groq_model,
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


def _clamp_score(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, numeric))


def _normalize_decision(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"match", "review", "reject"}:
        return normalized
    return "review"


def _fallback_review(
    summary: str,
    *,
    failure_cause: str,
    payload: dict[str, Any] | None = None,
) -> JobRelevanceResult:
    return JobRelevanceResult(
        decision="review",
        score=None,
        summary=summary,
        matched_signals=[],
        concerns=[failure_cause],
        source="system_fallback",
        model_name=None,
        failure_cause=failure_cause,
        payload=payload or {},
    )


def _classify_with_ai(
    client: OpenAI,
    model: str,
    profile: RoleProfile,
    *,
    title: str,
    company_name: str | None,
    location: str | None,
    source_type: str | None,
    apply_target_type: str | None,
    description_snippet: str | None,
    matched_titles: list[str],
) -> JobRelevanceResult:
    response = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a strict job relevance classifier for a personal job-application assistant. "
                    "Decide whether a job matches the user's role profile. "
                    "Prefer 'review' when uncertain. "
                    "Return JSON with keys: decision, score, summary, matched_signals, concerns. "
                    "Valid decision values are match, review, reject."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "role_profile": {
                            "prompt": profile.prompt,
                            "generated_titles": profile.generated_titles,
                        },
                        "job": {
                            "title": title,
                            "company_name": company_name,
                            "location": location,
                            "source_type": source_type,
                            "apply_target_type": apply_target_type,
                            "description_snippet": description_snippet,
                            "matched_titles": matched_titles,
                        },
                        "instructions": [
                            "Treat the role profile and matched title candidates as the source of truth.",
                            "The title already passed a deterministic title gate, so focus on whether the role still fits based on seniority, family, and context.",
                            "Use reject when the title is plausible but the job is still clearly outside the intended role profile.",
                            "Use review only for genuinely ambiguous borderline cases.",
                        ],
                    }
                ),
            },
        ],
    )

    payload = json.loads(_extract_completion_text(response))
    return JobRelevanceResult(
        decision=_normalize_decision(payload.get("decision")),
        score=_clamp_score(payload.get("score")),
        summary=str(payload.get("summary") or "AI relevance classifier did not provide a summary."),
        matched_signals=_normalize_list(list(payload.get("matched_signals", []))),
        concerns=_normalize_list(list(payload.get("concerns", []))),
        source="ai",
        model_name=model,
        failure_cause=None,
        payload=payload,
    )


def classify_job_relevance(
    profile: RoleProfile | None,
    *,
    title: str,
    company_name: str | None = None,
    location: str | None = None,
    source_type: str | None = None,
    apply_target_type: str | None = None,
    description_snippet: str | None = None,
    matched_titles: list[str] | None = None,
    settings: Settings | None = None,
    client: OpenAI | None = None,
) -> JobRelevanceResult:
    if not profile or not profile.prompt.strip():
        return JobRelevanceResult(
            decision="match",
            score=1.0,
            summary="No role profile configured, so the job stays visible by default.",
            matched_signals=[],
            concerns=[],
            source="system_fallback",
            model_name=None,
            failure_cause=None,
            payload={},
        )

    resolved_settings = settings or get_settings()
    configured_client, configured_model = _build_ai_client(resolved_settings)
    resolved_client = client or configured_client

    if resolved_client is None or not configured_model:
        return _fallback_review(
            "AI relevance classification is unavailable because the provider is not configured.",
            failure_cause="config_missing",
        )

    retry_attempts = max(1, getattr(resolved_settings, "relevance_retry_attempts", 2))
    retry_delay_seconds = max(
        0.05,
        float(getattr(resolved_settings, "relevance_retry_base_delay_seconds", 0.5)),
    )

    for attempt in range(retry_attempts):
        try:
            return _classify_with_ai(
                resolved_client,
                configured_model,
                profile,
                title=title,
                company_name=company_name,
                location=location,
                source_type=source_type,
                apply_target_type=apply_target_type,
                description_snippet=description_snippet,
                matched_titles=matched_titles or [],
            )
        except RateLimitError as error:
            if attempt < retry_attempts - 1:
                time.sleep(retry_delay_seconds * (2**attempt))
                continue
            return _fallback_review(
                "AI relevance classification was rate-limited, so this job needs review.",
                failure_cause="provider_rate_limited",
                payload={"error_type": type(error).__name__},
            )
        except (APITimeoutError, APIConnectionError) as error:
            if attempt < retry_attempts - 1:
                time.sleep(retry_delay_seconds * (2**attempt))
                continue
            return _fallback_review(
                "AI relevance classification timed out, so this job needs review.",
                failure_cause="provider_timeout",
                payload={"error_type": type(error).__name__},
            )
        except APIStatusError as error:
            if error.status_code == 429:
                if attempt < retry_attempts - 1:
                    time.sleep(retry_delay_seconds * (2**attempt))
                    continue
                return _fallback_review(
                    "AI relevance classification was rate-limited, so this job needs review.",
                    failure_cause="provider_rate_limited",
                    payload={"error_type": type(error).__name__, "status_code": error.status_code},
                )
            if error.status_code >= 500 and attempt < retry_attempts - 1:
                time.sleep(retry_delay_seconds * (2**attempt))
                continue
            return _fallback_review(
                "AI relevance classification is temporarily unavailable, so this job needs review.",
                failure_cause="provider_unavailable",
                payload={"error_type": type(error).__name__, "status_code": error.status_code},
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            return _fallback_review(
                "AI relevance classification returned an invalid response, so this job needs review.",
                failure_cause="provider_response_invalid",
                payload={"error_type": type(error).__name__},
            )
        except Exception as error:
            return _fallback_review(
                "AI relevance classification failed unexpectedly, so this job needs review.",
                failure_cause="provider_unavailable",
                payload={"error_type": type(error).__name__},
            )

    return _fallback_review(
        "AI relevance classification did not complete, so this job needs review.",
        failure_cause="provider_unavailable",
    )
