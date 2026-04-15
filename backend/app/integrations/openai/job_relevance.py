from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError

from app.config import Settings, get_settings
from app.domains.jobs.relevance_policy import build_role_context_for_screening, derive_profile_hints
from app.domains.role_profiles.models import RoleProfile


JOB_RELEVANCE_SCHEMA = {
    "name": "job_relevance_batch",
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
                        "job_index": {"type": "integer"},
                        "decision": {"type": "string", "enum": ["match", "review", "reject"]},
                        "score": {"type": "number"},
                        "summary": {"type": "string"},
                        "matched_signals": {"type": "array", "items": {"type": "string"}},
                        "concerns": {"type": "array", "items": {"type": "string"}},
                        "decision_rationale_type": {
                            "type": "string",
                            "enum": [
                                "family_match",
                                "specialization_only",
                                "clear_family_mismatch",
                                "clear_seniority_mismatch",
                                "seniority_uncertain",
                                "context_conflict",
                                "provider_fallback",
                                "adjacent_level_variant",
                            ],
                        },
                        "role_family_alignment": {
                            "type": "string",
                            "enum": ["same_family", "adjacent_family", "different_family", "uncertain"],
                        },
                        "seniority_alignment": {
                            "type": "string",
                            "enum": ["same_band", "adjacent_or_same", "more_senior", "more_junior", "uncertain"],
                        },
                        "modifier_impact": {
                            "type": "string",
                            "enum": ["none", "specialization_only", "material_scope_change", "uncertain"],
                        },
                        "contradiction_strength": {
                            "type": "string",
                            "enum": ["none", "weak", "moderate", "strong"],
                        },
                    },
                    "required": [
                        "job_index",
                        "decision",
                        "score",
                        "summary",
                        "matched_signals",
                        "concerns",
                        "decision_rationale_type",
                        "role_family_alignment",
                        "seniority_alignment",
                        "modifier_impact",
                        "contradiction_strength",
                    ],
                },
            }
        },
        "required": ["results"],
    },
}

JOB_RELEVANCE_SINGLE_SCHEMA = {
    "name": "job_relevance_single",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "decision": {"type": "string", "enum": ["match", "review", "reject"]},
            "score": {"type": "number"},
            "summary": {"type": "string"},
            "matched_signals": {"type": "array", "items": {"type": "string"}},
            "concerns": {"type": "array", "items": {"type": "string"}},
            "decision_rationale_type": {
                "type": "string",
                "enum": [
                    "family_match",
                    "specialization_only",
                    "clear_family_mismatch",
                    "clear_seniority_mismatch",
                    "seniority_uncertain",
                    "context_conflict",
                    "provider_fallback",
                    "adjacent_level_variant",
                ],
            },
            "role_family_alignment": {
                "type": "string",
                "enum": ["same_family", "adjacent_family", "different_family", "uncertain"],
            },
            "seniority_alignment": {
                "type": "string",
                "enum": ["same_band", "adjacent_or_same", "more_senior", "more_junior", "uncertain"],
            },
            "modifier_impact": {
                "type": "string",
                "enum": ["none", "specialization_only", "material_scope_change", "uncertain"],
            },
            "contradiction_strength": {
                "type": "string",
                "enum": ["none", "weak", "moderate", "strong"],
            },
        },
        "required": [
            "decision",
            "score",
            "summary",
            "matched_signals",
            "concerns",
            "decision_rationale_type",
            "role_family_alignment",
            "seniority_alignment",
            "modifier_impact",
            "contradiction_strength",
        ],
    },
}


def _json_schema_response_format(schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema["name"],
            "schema": schema["schema"],
            "strict": False,
        },
    }


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


@dataclass(slots=True)
class JobRelevanceBatchRequest:
    title: str
    company_name: str | None
    location: str | None
    source_type: str | None
    apply_target_type: str | None
    description_snippet: str | None
    matched_titles: list[str]
    title_screening_decision: str | None
    title_screening_summary: str | None
    title_screening_source: str | None


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
            settings.groq_job_relevance_model or settings.groq_model,
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


def _normalize_rationale_type(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    if normalized in {
        "family_match",
        "specialization_only",
        "clear_family_mismatch",
        "clear_seniority_mismatch",
        "seniority_uncertain",
        "context_conflict",
        "provider_fallback",
        "adjacent_level_variant",
    }:
        return normalized
    return "context_conflict"


def _normalize_role_family_alignment(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"same_family", "adjacent_family", "different_family", "uncertain"}:
        return normalized
    return None


def _normalize_seniority_alignment(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"same_band", "adjacent_or_same", "more_senior", "more_junior", "uncertain"}:
        return normalized
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


def _relevance_payload_inconsistent(*, decision: str, payload: dict[str, Any]) -> bool:
    family = _normalize_role_family_alignment(payload.get("role_family_alignment"))
    seniority = _normalize_seniority_alignment(payload.get("seniority_alignment"))
    modifier = _normalize_modifier_impact(payload.get("modifier_impact"))
    contradiction = _normalize_contradiction_strength(payload.get("contradiction_strength"))

    if None in {family, seniority, modifier, contradiction}:
        return True
    if decision == "match" and family == "different_family":
        return True
    if decision == "match" and contradiction in {"moderate", "strong"}:
        return True
    if (
        decision == "reject"
        and family == "same_family"
        and seniority in {"same_band", "adjacent_or_same"}
        and modifier in {"none", "specialization_only"}
        and contradiction in {"none", "weak"}
    ):
        return True
    if (
        decision == "review"
        and family in {"same_family", "adjacent_family"}
        and seniority in {"same_band", "adjacent_or_same"}
        and contradiction in {"none", "weak"}
    ):
        return True
    return False


def _normalize_text(value: str) -> str:
    return " ".join(value.lower().replace("-", " ").split())


def _default_summary_for_decision(decision: str) -> str:
    if decision == "match":
        return "The job appears aligned with the target role family and level."
    if decision == "reject":
        return "The job appears outside the intended role family or level."
    return "The job looks related, but the available context leaves some uncertainty about fit."


def _sanitize_summary(*, title: str, company_name: str | None, decision: str, summary: Any) -> str:
    raw_summary = str(summary or "").strip()
    if not raw_summary:
        return _default_summary_for_decision(decision)
    normalized_summary = _normalize_text(raw_summary)
    normalized_title = _normalize_text(title)
    normalized_company = _normalize_text(company_name or "")
    if normalized_summary == normalized_title:
        return _default_summary_for_decision(decision)
    if normalized_company and normalized_summary == f"{normalized_title} role at {normalized_company}":
        return _default_summary_for_decision(decision)
    return raw_summary


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


def _repair_with_ai(
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
    title_screening_decision: str | None,
    title_screening_summary: str | None,
    title_screening_source: str | None,
    decision_policy: dict[str, str | bool] | None,
    derived_profile_hints: dict[str, str | bool] | None,
    original_payload: dict[str, Any],
) -> dict[str, Any]:
    response = client.chat.completions.create(
        model=model,
        response_format=_json_schema_response_format(JOB_RELEVANCE_SINGLE_SCHEMA),
        messages=[
            {
                "role": "system",
                "content": (
                    "Repair a job relevance decision so the final decision and structured fields are internally consistent. "
                    "Return JSON with keys decision, score, summary, matched_signals, concerns, decision_rationale_type, role_family_alignment, seniority_alignment, modifier_impact, and contradiction_strength. "
                    "Valid decisions are match, review, reject."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "role_profile": {"prompt": profile.prompt},
                        "derived_profile_hints": derived_profile_hints or {},
                        "decision_policy": decision_policy or {},
                        "job": {
                            "title": title,
                            "company_name": company_name,
                            "location": location,
                            "source_type": source_type,
                            "apply_target_type": apply_target_type,
                            "description_snippet": description_snippet,
                            "matched_titles": matched_titles,
                            "title_screening": {
                                "decision": title_screening_decision,
                                "summary": title_screening_summary,
                                "source": title_screening_source,
                            },
                        },
                        "previous_result": original_payload,
                        "instructions": [
                            "A title that already passed title screening is a strong positive prior, but different role families should not be marked match.",
                            "Specialization-only differences should not force review or reject.",
                            "If the job is clearly a different family, reject.",
                            "If the job remains same-family and same-level or adjacent-level with no strong contradiction, prefer match.",
                        ],
                    }
                ),
            },
        ],
    )
    payload = json.loads(_extract_completion_text(response))
    decision = _normalize_decision(payload.get("decision"))
    if _relevance_payload_inconsistent(decision=decision, payload=payload):
        return {
            "decision": "review",
            "score": None,
            "summary": "AI repair produced an inconsistent result, so the job needs manual review.",
            "matched_signals": [],
            "concerns": ["repair_response_inconsistent"],
            "decision_rationale_type": "context_conflict",
            "role_family_alignment": "uncertain",
            "seniority_alignment": "uncertain",
            "modifier_impact": "uncertain",
            "contradiction_strength": "moderate",
        }
    return payload


def _default_review_from_missing_batch_result() -> JobRelevanceResult:
    return JobRelevanceResult(
        decision="review",
        score=None,
        summary="AI relevance classification did not return a result for this job, so it needs review.",
        matched_signals=[],
        concerns=["provider_response_invalid"],
        source="system_fallback",
        model_name=None,
        failure_cause="provider_response_invalid",
        payload={},
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
    title_screening_decision: str | None,
    title_screening_summary: str | None,
    title_screening_source: str | None,
    decision_policy: dict[str, str | bool] | None,
    derived_profile_hints: dict[str, str | bool] | None,
) -> JobRelevanceResult:
    hints = derived_profile_hints or {}
    role_context = build_role_context_for_screening(profile.prompt, hints)
    role_context_prefix = (role_context + " ") if role_context else ""
    response = client.chat.completions.create(
        model=model,
        response_format=_json_schema_response_format(JOB_RELEVANCE_SINGLE_SCHEMA),
        messages=[
            {
                "role": "system",
                "content": (
                    f"{role_context_prefix}"
                    "You are a strict job relevance classifier for a personal job-application assistant. "
                    "Decide whether a job matches the user's role profile. "
                    "These jobs have already gone through title screening, so do not treat harmless wording differences or specializations as ambiguity by default. "
                    "Treat a passed title as strong evidence that the role family is already in scope unless the richer context clearly contradicts it. "
                    "Prefer 'match' when the role family and likely level fit the user's profile and there is no strong contradictory evidence in the available context. "
                    "Treat alternate job title wordings that imply the same kind of work as equivalent — minor label differences are not a reason for uncertainty. "
                    "Treat neighboring early-career indicators and adjacent entry-level signals as generally compatible unless the context clearly shows a different seniority band. "
                    "Do not assume that adjacent early-career wording, associate labels, or level-1 style indicators are too senior unless the richer context clearly shows a materially different level. "
                    "Do not treat specialization, team, platform, domain, technology, or focus-area modifiers as evidence against fit by default. "
                    "Do not treat same-industry adjacency or broad technical similarity as enough for a match when the underlying discipline is different. "
                    "A slash in a title (e.g. Engineer/Tester) does not automatically create uncertainty — only use review if the secondary role is a genuinely different discipline that dominates the role. "
                    "Use 'review' only when the available information creates real uncertainty after considering the already-passed title and the richer context. "
                    "Write a concise summary that explains the reasoning and does not simply restate the title or company name. "
                    "Valid decision values are match, review, reject."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "role_profile": {
                            "prompt": profile.prompt,
                        },
                        "derived_profile_hints": hints,
                        "decision_policy": decision_policy or {},
                        "job": {
                            "title": title,
                            "company_name": company_name,
                            "location": location,
                            "source_type": source_type,
                            "apply_target_type": apply_target_type,
                            "description_snippet": description_snippet,
                            "matched_titles": matched_titles,
                            "title_screening": {
                                "decision": title_screening_decision,
                                "summary": title_screening_summary,
                                "source": title_screening_source,
                            },
                        },
                        "instructions": [
                            "Treat the role profile prompt and title screening result as the source of truth.",
                            "The title already passed AI title screening, so focus on whether the richer context disqualifies it rather than re-litigating harmless title differences.",
                            "Do not use review just because the title wording is not an exact match to the user's prompt.",
                            "Do not use review just because the title includes specialization, team, domain, technology, or focus modifiers.",
                            "Alternate title wordings that imply the same kind of work are not a reason for uncertainty — treat them as equivalent.",
                            "If the role is still clearly within the intended family and likely level, prefer match.",
                            "Do not use review just because the title uses adjacent entry-level wording or level-1 style labels.",
                            "Do not infer that a role is too senior unless the richer context provides clear evidence of that.",
                            "Only use review when the richer context leaves meaningful uncertainty about whether the role actually fits.",
                            "Use reject when the title is plausible but the job is still clearly outside the intended role profile.",
                            "Do not use review for normal in-family roles just because the wording is broader or slightly different from the prompt.",
                            "Your structured fields must support your final decision.",
                            "If the role family is the same or adjacent, seniority is same or adjacent, modifiers are only specialization, and contradiction strength is none or weak, the decision should usually be match rather than review.",
                        ],
                    }
                ),
            },
        ],
    )

    payload = json.loads(_extract_completion_text(response))
    decision = _normalize_decision(payload.get("decision"))
    if _relevance_payload_inconsistent(decision=decision, payload=payload):
        payload = _repair_with_ai(
            client,
            model,
            profile,
            title=title,
            company_name=company_name,
            location=location,
            source_type=source_type,
            apply_target_type=apply_target_type,
            description_snippet=description_snippet,
            matched_titles=matched_titles,
            title_screening_decision=title_screening_decision,
            title_screening_summary=title_screening_summary,
            title_screening_source=title_screening_source,
            decision_policy=decision_policy,
            derived_profile_hints=derived_profile_hints,
            original_payload=payload,
        )
        decision = _normalize_decision(payload.get("decision"))
    return JobRelevanceResult(
        decision=decision,
        score=_clamp_score(payload.get("score")),
        summary=_sanitize_summary(
            title=title,
            company_name=company_name,
            decision=decision,
            summary=payload.get("summary"),
        ),
        matched_signals=_normalize_list(list(payload.get("matched_signals", []))),
        concerns=_normalize_list(list(payload.get("concerns", []))),
        source="ai",
        model_name=model,
        failure_cause=None,
        payload={**payload, **_structured_fields_payload(payload)},
    )


def _classify_batch_with_ai(
    client: OpenAI,
    model: str,
    profile: RoleProfile,
    *,
    jobs: list[JobRelevanceBatchRequest],
    decision_policy: dict[str, str | bool] | None,
    derived_profile_hints: dict[str, str | bool] | None,
) -> list[JobRelevanceResult]:
    hints = derived_profile_hints or {}
    role_context = build_role_context_for_screening(profile.prompt, hints)
    role_context_prefix = (role_context + " ") if role_context else ""
    response = client.chat.completions.create(
        model=model,
        response_format=_json_schema_response_format(JOB_RELEVANCE_SCHEMA),
        messages=[
            {
                "role": "system",
                "content": (
                    f"{role_context_prefix}"
                    "You are a strict job relevance classifier for a personal job-application assistant. "
                    "Decide whether each job matches the user's role profile. "
                    "These jobs have already gone through title screening, so do not treat harmless wording differences or specializations as ambiguity by default. "
                    "Treat a passed title as strong evidence that the role family is already in scope unless the richer context clearly contradicts it. "
                    "Prefer 'match' when the role family and likely level fit the user's profile and there is no strong contradictory evidence in the available context. "
                    "Treat alternate job title wordings that imply the same kind of work as equivalent — minor label differences are not a reason for uncertainty. "
                    "Treat neighboring early-career indicators and adjacent entry-level signals as generally compatible unless the context clearly shows a different seniority band. "
                    "Do not assume that adjacent early-career wording, associate labels, or level-1 style indicators are too senior unless the richer context clearly shows a materially different level. "
                    "Do not treat specialization, team, platform, domain, technology, or focus-area modifiers as evidence against fit by default. "
                    "Do not treat same-industry adjacency or broad technical similarity as enough for a match when the underlying discipline is different. "
                    "A slash in a title (e.g. Engineer/Tester) does not automatically create uncertainty — only use review if the secondary role is a genuinely different discipline that dominates the role. "
                    "Use 'review' only when the available information creates real uncertainty after considering the already-passed title and the richer context. "
                    "Write concise summaries that explain the reasoning and do not simply restate the title or company name. "
                    "Return JSON with a single key 'results'. "
                    "Each item in results must include job_index, decision, score, summary, matched_signals, concerns, decision_rationale_type, role_family_alignment, seniority_alignment, modifier_impact, and contradiction_strength. "
                    "Valid decision values are match, review, reject."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "role_profile": {
                            "prompt": profile.prompt,
                        },
                        "derived_profile_hints": hints,
                        "decision_policy": decision_policy or {},
                        "jobs": [
                            {
                                "job_index": index,
                                "title": job.title,
                                "company_name": job.company_name,
                                "location": job.location,
                                "source_type": job.source_type,
                                "apply_target_type": job.apply_target_type,
                                "description_snippet": job.description_snippet,
                                "matched_titles": job.matched_titles,
                                "title_screening": {
                                    "decision": job.title_screening_decision,
                                    "summary": job.title_screening_summary,
                                    "source": job.title_screening_source,
                                },
                            }
                            for index, job in enumerate(jobs)
                        ],
                        "instructions": [
                            "Treat the role profile prompt and title screening result as the source of truth.",
                            "Only these jobs already passed title screening, so focus on whether the richer context disqualifies them rather than re-litigating harmless title differences.",
                            "Do not use review just because the title wording is not an exact match to the user's prompt.",
                            "Do not use review just because the title includes specialization, team, domain, technology, or focus modifiers.",
                            "Alternate title wordings that imply the same kind of work are not a reason for uncertainty — treat them as equivalent.",
                            "If the role is still clearly within the intended family and likely level, prefer match.",
                            "Do not use review just because the title uses adjacent entry-level wording or level-1 style labels.",
                            "Do not infer that a role is too senior unless the richer context provides clear evidence of that.",
                            "Only use review when the richer context leaves meaningful uncertainty about whether the role actually fits.",
                            "Use reject when the title is plausible but the job is still clearly outside the intended role profile.",
                            "Do not use review for normal in-family roles just because the wording is broader or slightly different from the prompt.",
                            "Your structured fields must support your final decision.",
                            "If the role family is the same or adjacent, seniority is same or adjacent, modifiers are only specialization, and contradiction strength is none or weak, the decision should usually be match rather than review.",
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

    results_by_index: dict[int, JobRelevanceResult] = {}
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            raise TypeError("result item must be an object")
        job_index = raw_item.get("job_index")
        if not isinstance(job_index, int) or job_index < 0 or job_index >= len(jobs):
            raise ValueError("result item missing a valid job_index")
        decision = _normalize_decision(raw_item.get("decision"))
        if _relevance_payload_inconsistent(decision=decision, payload=raw_item):
            repaired_payload = _repair_with_ai(
                client,
                model,
                profile,
                title=jobs[job_index].title,
                company_name=jobs[job_index].company_name,
                location=jobs[job_index].location,
                source_type=jobs[job_index].source_type,
                apply_target_type=jobs[job_index].apply_target_type,
                description_snippet=jobs[job_index].description_snippet,
                matched_titles=jobs[job_index].matched_titles,
                title_screening_decision=jobs[job_index].title_screening_decision,
                title_screening_summary=jobs[job_index].title_screening_summary,
                title_screening_source=jobs[job_index].title_screening_source,
                decision_policy=decision_policy,
                derived_profile_hints=derived_profile_hints,
                original_payload=raw_item,
            )
            raw_item = repaired_payload
            decision = _normalize_decision(raw_item.get("decision"))
        results_by_index[job_index] = JobRelevanceResult(
            decision=decision,
            score=_clamp_score(raw_item.get("score")),
            summary=_sanitize_summary(
                title=jobs[job_index].title,
                company_name=jobs[job_index].company_name,
                decision=decision,
                summary=raw_item.get("summary"),
            ),
            matched_signals=_normalize_list(list(raw_item.get("matched_signals", []))),
            concerns=_normalize_list(list(raw_item.get("concerns", []))),
            source="ai",
            model_name=model,
            failure_cause=None,
            payload={**raw_item, **_structured_fields_payload(raw_item)},
        )

    return [results_by_index.get(index, _default_review_from_missing_batch_result()) for index in range(len(jobs))]


def classify_job_relevance_batch(
    profile: RoleProfile | None,
    jobs: list[JobRelevanceBatchRequest],
    *,
    decision_policy: dict[str, str | bool] | None = None,
    derived_profile_hints: dict[str, str | bool] | None = None,
    settings: Settings | None = None,
    client: OpenAI | None = None,
) -> list[JobRelevanceResult]:
    if not jobs:
        return []

    if not profile or not profile.prompt.strip():
        return [
            JobRelevanceResult(
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
            for _ in jobs
        ]

    resolved_settings = settings or get_settings()
    configured_client, configured_model = _build_ai_client(resolved_settings)
    resolved_client = client or configured_client

    if resolved_client is None or not configured_model:
        return [
            _fallback_review(
                "AI relevance classification is unavailable because the provider is not configured.",
                failure_cause="config_missing",
            )
            for _ in jobs
        ]

    retry_attempts = max(1, getattr(resolved_settings, "relevance_retry_attempts", 2))
    retry_delay_seconds = max(
        0.05,
        float(getattr(resolved_settings, "relevance_retry_base_delay_seconds", 0.5)),
    )

    for attempt in range(retry_attempts):
        try:
            return _classify_batch_with_ai(
                resolved_client,
                configured_model,
                profile,
                jobs=jobs,
                decision_policy=decision_policy,
                derived_profile_hints=derived_profile_hints,
            )
        except RateLimitError as error:
            if attempt < retry_attempts - 1:
                time.sleep(retry_delay_seconds * (2**attempt))
                continue
            return [
                _fallback_review(
                    "AI relevance classification was rate-limited, so this job needs review.",
                    failure_cause="provider_rate_limited",
                    payload={"error_type": type(error).__name__},
                )
                for _ in jobs
            ]
        except (APITimeoutError, APIConnectionError) as error:
            if attempt < retry_attempts - 1:
                time.sleep(retry_delay_seconds * (2**attempt))
                continue
            return [
                _fallback_review(
                    "AI relevance classification timed out, so this job needs review.",
                    failure_cause="provider_timeout",
                    payload={"error_type": type(error).__name__},
                )
                for _ in jobs
            ]
        except APIStatusError as error:
            if error.status_code == 429 and attempt < retry_attempts - 1:
                time.sleep(retry_delay_seconds * (2**attempt))
                continue
            failure_cause = "provider_rate_limited" if error.status_code == 429 else "provider_unavailable"
            summary = (
                "AI relevance classification was rate-limited, so this job needs review."
                if failure_cause == "provider_rate_limited"
                else "AI relevance classification is temporarily unavailable, so this job needs review."
            )
            return [
                _fallback_review(
                    summary,
                    failure_cause=failure_cause,
                    payload={"error_type": type(error).__name__, "status_code": error.status_code},
                )
                for _ in jobs
            ]
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            return [
                _fallback_review(
                    "AI relevance classification returned an invalid response, so this job needs review.",
                    failure_cause="provider_response_invalid",
                    payload={"error_type": type(error).__name__},
                )
                for _ in jobs
            ]
        except Exception as error:
            return [
                _fallback_review(
                    "AI relevance classification failed unexpectedly, so this job needs review.",
                    failure_cause="provider_unavailable",
                    payload={"error_type": type(error).__name__},
                )
                for _ in jobs
            ]

    return [
        _fallback_review(
            "AI relevance classification did not complete, so this job needs review.",
            failure_cause="provider_unavailable",
        )
        for _ in jobs
    ]


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
    title_screening_decision: str | None = None,
    title_screening_summary: str | None = None,
    title_screening_source: str | None = None,
    decision_policy: dict[str, str | bool] | None = None,
    derived_profile_hints: dict[str, str | bool] | None = None,
    settings: Settings | None = None,
    client: OpenAI | None = None,
) -> JobRelevanceResult:
    return classify_job_relevance_batch(
        profile,
        [
            JobRelevanceBatchRequest(
                title=title,
                company_name=company_name,
                location=location,
                source_type=source_type,
                apply_target_type=apply_target_type,
                description_snippet=description_snippet,
                matched_titles=matched_titles or [],
                title_screening_decision=title_screening_decision,
                title_screening_summary=title_screening_summary,
                title_screening_source=title_screening_source,
            )
        ],
        decision_policy=decision_policy,
        derived_profile_hints=derived_profile_hints,
        settings=settings,
        client=client,
    )[0]
