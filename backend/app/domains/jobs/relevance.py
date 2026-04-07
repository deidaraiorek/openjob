from __future__ import annotations

import hashlib
import json

from sqlalchemy.orm import Session

from app.domains.jobs.deduplication import DiscoveryCandidate
from app.domains.jobs.models import Job, JobRelevanceEvaluation
from app.domains.role_profiles.models import RoleProfile
from app.integrations.openai.job_relevance import (
    JobRelevanceBatchRequest,
    JobRelevanceResult,
    classify_job_relevance,
)
from app.integrations.openai.job_title_screening import classify_job_titles


def profile_snapshot_hash(profile: RoleProfile | None) -> str | None:
    if not profile:
        return None

    payload = {
        "prompt": profile.prompt,
    }
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _extract_description_snippet(candidate: DiscoveryCandidate | None, job: Job | None) -> str | None:
    raw_payload = {}
    if candidate is not None:
        raw_payload = candidate.raw_payload
    for key in ("description", "content", "body", "text"):
        value = raw_payload.get(key)
        if isinstance(value, str) and value.strip():
            return " ".join(value.strip().split())[:800]
    return None


def job_context_fingerprint(
    *,
    title: str,
    company_name: str | None,
    location: str | None,
    source_type: str | None,
    apply_target_type: str | None,
    description_snippet: str | None,
) -> str:
    payload = {
        "title": title,
        "company_name": company_name,
        "location": location,
        "source_type": source_type,
        "apply_target_type": apply_target_type,
        "description_snippet": description_snippet,
    }
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def cached_relevance_for_job(
    profile: RoleProfile | None,
    job: Job,
    *,
    source_type: str | None,
    apply_target_type: str | None,
    description_snippet: str | None,
) -> JobRelevanceResult | None:
    latest_evaluation = job.relevance_evaluations[0] if job.relevance_evaluations else None
    if latest_evaluation is None:
        return None
    if latest_evaluation.payload.get("failure_cause") is not None:
        return None
    if latest_evaluation.source == "system_fallback":
        return None

    expected_profile_hash = profile_snapshot_hash(profile)
    cached_profile_hash = latest_evaluation.profile_snapshot_hash
    if expected_profile_hash != cached_profile_hash:
        return None

    expected_fingerprint = job_context_fingerprint(
        title=job.title,
        company_name=job.company_name,
        location=job.location,
        source_type=source_type,
        apply_target_type=apply_target_type,
        description_snippet=description_snippet,
    )
    cached_fingerprint = latest_evaluation.payload.get("job_fingerprint")
    if expected_fingerprint != cached_fingerprint:
        return None

    return JobRelevanceResult(
        decision=latest_evaluation.decision,
        score=latest_evaluation.score,
        summary=latest_evaluation.summary or "Cached relevance evaluation reused.",
        matched_signals=latest_evaluation.matched_signals,
        concerns=latest_evaluation.concerns,
        source=latest_evaluation.source,
        model_name=latest_evaluation.model_name,
        failure_cause=latest_evaluation.payload.get("failure_cause"),
        payload=latest_evaluation.payload,
    )


def evaluate_candidate_relevance(
    profile: RoleProfile | None,
    candidate: DiscoveryCandidate,
    *,
    screening: ScreenedTitle | None = None,
) -> JobRelevanceResult:
    resolved_screening = screening
    if resolved_screening is None:
        title_screen = screen_candidate_titles(profile, [candidate])
        resolved_screening = title_screen[candidate.title]
    if resolved_screening.decision == "reject":
        return title_screen_reject_result(candidate.title, resolved_screening)

    description_snippet = _extract_description_snippet(candidate, None)
    return classify_job_relevance(
        profile,
        title=candidate.title,
        company_name=candidate.company_name,
        location=candidate.location,
        source_type=candidate.source_type,
        apply_target_type=candidate.apply_target_type,
        description_snippet=description_snippet,
        matched_titles=[candidate.title],
        title_screening_decision=resolved_screening.decision,
        title_screening_summary=resolved_screening.summary,
        title_screening_source=resolved_screening.source,
    )


def evaluate_job_relevance(
    profile: RoleProfile | None,
    job: Job,
) -> JobRelevanceResult:
    preferred_target = next((target for target in job.apply_targets if target.is_preferred), None)
    latest_sighting = max(job.sightings, key=lambda item: item.id, default=None)
    candidate = None
    if latest_sighting is not None:
        candidate = DiscoveryCandidate(
            source_type=latest_sighting.source.source_type if latest_sighting.source else "unknown",
            company_name=job.company_name,
            title=job.title,
            listing_url=latest_sighting.listing_url,
            external_job_id=latest_sighting.external_job_id,
            location=job.location,
            apply_url=latest_sighting.apply_url,
            apply_target_type=preferred_target.target_type if preferred_target else None,
            raw_payload=latest_sighting.raw_payload,
        )

    description_snippet = _extract_description_snippet(candidate, job)
    cached_result = cached_relevance_for_job(
        profile,
        job,
        source_type=candidate.source_type if candidate else None,
        apply_target_type=preferred_target.target_type if preferred_target else None,
        description_snippet=description_snippet,
    )
    if cached_result is not None:
        return cached_result

    title_screen = screen_candidate_titles(profile, [candidate] if candidate else [])
    screening = title_screen.get(job.title)
    if screening is None and candidate is None:
        screening = screen_candidate_title(profile, job.title)
    if screening and screening.decision == "reject":
        return title_screen_reject_result(job.title, screening)

    return classify_job_relevance(
        profile,
        title=job.title,
        company_name=job.company_name,
        location=job.location,
        source_type=candidate.source_type if candidate else None,
        apply_target_type=preferred_target.target_type if preferred_target else None,
        description_snippet=description_snippet,
        matched_titles=[job.title],
        title_screening_decision=screening.decision if screening else None,
        title_screening_summary=screening.summary if screening else None,
        title_screening_source=screening.source if screening else None,
    )


class ScreenedTitle:
    __slots__ = ("title", "decision", "summary", "source", "model_name", "failure_cause", "payload")

    def __init__(
        self,
        *,
        title: str,
        decision: str,
        summary: str,
        source: str,
        model_name: str | None,
        failure_cause: str | None,
        payload: dict[str, object],
    ) -> None:
        self.title = title
        self.decision = decision
        self.summary = summary
        self.source = source
        self.model_name = model_name
        self.failure_cause = failure_cause
        self.payload = payload


def screen_candidate_title(profile: RoleProfile | None, title: str) -> ScreenedTitle:
    result = classify_job_titles(profile.prompt if profile else None, [title])
    item = result.items[0]
    return ScreenedTitle(
        title=item.title,
        decision=item.decision,
        summary=item.summary,
        source=result.source,
        model_name=result.model_name,
        failure_cause=result.failure_cause,
        payload=result.payload,
    )


def screen_candidate_titles(
    profile: RoleProfile | None,
    candidates: list[DiscoveryCandidate],
) -> dict[str, ScreenedTitle]:
    titles = [candidate.title for candidate in candidates]
    result = classify_job_titles(profile.prompt if profile else None, titles)
    return {
        item.title: ScreenedTitle(
            title=item.title,
            decision=item.decision,
            summary=item.summary,
            source=result.source,
            model_name=result.model_name,
            failure_cause=result.failure_cause,
            payload=result.payload,
        )
        for item in result.items
    }


def title_screen_reject_result(title: str, screening: ScreenedTitle) -> JobRelevanceResult:
    return JobRelevanceResult(
        decision="reject",
        score=0.0,
        summary=screening.summary,
        matched_signals=[title],
        concerns=["title_screening"],
        source="title_screening",
        model_name=screening.model_name,
        failure_cause=screening.failure_cause,
        payload={
            "screening_decision": screening.decision,
            "screening_summary": screening.summary,
            "screening_source": screening.source,
            "screening_payload": screening.payload,
        },
    )


def title_screen_review_result(title: str, screening: ScreenedTitle) -> JobRelevanceResult:
    return JobRelevanceResult(
        decision="review",
        score=None,
        summary=screening.summary,
        matched_signals=[title],
        concerns=["title_screening_review"],
        source="title_screening",
        model_name=screening.model_name,
        failure_cause=screening.failure_cause,
        payload={
            "screening_decision": screening.decision,
            "screening_summary": screening.summary,
            "screening_source": screening.source,
            "screening_payload": screening.payload,
        },
    )


def queued_relevance_result(
    title: str,
    screening: ScreenedTitle,
    *,
    summary: str,
    failure_cause: str,
) -> JobRelevanceResult:
    return JobRelevanceResult(
        decision="review",
        score=None,
        summary=summary,
        matched_signals=[title],
        concerns=["queued_relevance"],
        source="relevance_queue",
        model_name=screening.model_name,
        failure_cause=failure_cause,
        payload={
            "screening_decision": screening.decision,
            "screening_summary": screening.summary,
            "screening_source": screening.source,
            "screening_payload": screening.payload,
        },
    )


def build_batch_request_for_job(job: Job) -> JobRelevanceBatchRequest:
    preferred_target = next((target for target in job.apply_targets if target.is_preferred), None)
    latest_sighting = max(job.sightings, key=lambda item: item.id, default=None)
    candidate = None
    if latest_sighting is not None:
        candidate = DiscoveryCandidate(
            source_type=latest_sighting.source.source_type if latest_sighting.source else "unknown",
            company_name=job.company_name,
            title=job.title,
            listing_url=latest_sighting.listing_url,
            external_job_id=latest_sighting.external_job_id,
            location=job.location,
            apply_url=latest_sighting.apply_url,
            apply_target_type=preferred_target.target_type if preferred_target else None,
            raw_payload=latest_sighting.raw_payload,
        )

    latest_evaluation = job.relevance_evaluations[0] if job.relevance_evaluations else None
    payload = latest_evaluation.payload if latest_evaluation is not None else {}

    return JobRelevanceBatchRequest(
        title=job.title,
        company_name=job.company_name,
        location=job.location,
        source_type=candidate.source_type if candidate else None,
        apply_target_type=preferred_target.target_type if preferred_target else None,
        description_snippet=_extract_description_snippet(candidate, job),
        matched_titles=[job.title],
        title_screening_decision=payload.get("screening_decision"),
        title_screening_summary=payload.get("screening_summary"),
        title_screening_source=payload.get("screening_source"),
    )


def apply_relevance_result(
    session: Session,
    *,
    account_id: int,
    job: Job,
    result: JobRelevanceResult,
    profile: RoleProfile | None,
) -> JobRelevanceEvaluation:
    job.relevance_decision = result.decision
    job.relevance_source = result.source
    job.relevance_score = result.score
    job.relevance_summary = result.summary

    preferred_target = next((target for target in job.apply_targets if target.is_preferred), None)
    latest_sighting = max(job.sightings, key=lambda item: item.id, default=None)
    fingerprint_candidate = None
    if latest_sighting is not None:
        fingerprint_candidate = DiscoveryCandidate(
            source_type=latest_sighting.source.source_type if latest_sighting.source else "unknown",
            company_name=job.company_name,
            title=job.title,
            listing_url=latest_sighting.listing_url,
            external_job_id=latest_sighting.external_job_id,
            location=job.location,
            apply_url=latest_sighting.apply_url,
            apply_target_type=preferred_target.target_type if preferred_target else None,
            raw_payload=latest_sighting.raw_payload,
        )
    description_snippet = _extract_description_snippet(fingerprint_candidate, job)
    fingerprint = job_context_fingerprint(
        title=job.title,
        company_name=job.company_name,
        location=job.location,
        source_type=latest_sighting.source.source_type if latest_sighting and latest_sighting.source else None,
        apply_target_type=preferred_target.target_type if preferred_target else None,
        description_snippet=description_snippet,
    )
    evaluation_payload = dict(result.payload)
    evaluation_payload["job_fingerprint"] = fingerprint
    evaluation_payload["failure_cause"] = result.failure_cause
    evaluation_payload["decision_phase"] = (
        "title_screening"
        if result.source == "title_screening"
        else "full_relevance"
        if result.source in {"ai", "system_fallback", "manual_include", "manual_exclude", "manual_review"}
        else "relevance_queue"
        if result.source == "relevance_queue"
        else result.source
    )

    evaluation = JobRelevanceEvaluation(
        account_id=account_id,
        job_id=job.id,
        decision=result.decision,
        source=result.source,
        score=result.score,
        summary=result.summary,
        matched_signals=result.matched_signals,
        concerns=result.concerns,
        model_name=result.model_name,
        profile_snapshot_hash=profile_snapshot_hash(profile),
        payload=evaluation_payload,
    )
    session.add(evaluation)
    session.flush()
    return evaluation
