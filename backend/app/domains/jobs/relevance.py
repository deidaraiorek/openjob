from __future__ import annotations

import hashlib
import json

from sqlalchemy.orm import Session

from app.domains.jobs.deduplication import DiscoveryCandidate
from app.domains.jobs.models import Job, JobRelevanceEvaluation
from app.domains.jobs.title_matching import TitleMatchResult, match_title_against_catalog
from app.domains.role_profiles.models import RoleProfile
from app.integrations.openai.job_relevance import JobRelevanceResult, classify_job_relevance


def profile_snapshot_hash(profile: RoleProfile | None) -> str | None:
    if not profile:
        return None

    payload = {
        "prompt": profile.prompt,
        "generated_titles": profile.generated_titles,
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
) -> JobRelevanceResult:
    title_match = match_candidate_title(profile, candidate.title)
    if not title_match.matched:
        return title_gate_reject_result(title_match)

    description_snippet = _extract_description_snippet(candidate, None)
    return classify_job_relevance(
        profile,
        title=candidate.title,
        company_name=candidate.company_name,
        location=candidate.location,
        source_type=candidate.source_type,
        apply_target_type=candidate.apply_target_type,
        description_snippet=description_snippet,
        matched_titles=title_match.matched_titles,
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

    title_match = match_candidate_title(profile, job.title)
    if not title_match.matched:
        return title_gate_reject_result(title_match)

    return classify_job_relevance(
        profile,
        title=job.title,
        company_name=job.company_name,
        location=job.location,
        source_type=candidate.source_type if candidate else None,
        apply_target_type=preferred_target.target_type if preferred_target else None,
        description_snippet=description_snippet,
        matched_titles=title_match.matched_titles,
    )


def match_candidate_title(profile: RoleProfile | None, title: str) -> TitleMatchResult:
    if not profile or not profile.generated_titles:
        return TitleMatchResult(
            matched=True,
            normalized_title=title,
            matched_titles=[],
            summary="No generated title catalog is available, so the title stays eligible for AI review.",
        )
    return match_title_against_catalog(title, profile.generated_titles)


def title_gate_reject_result(match: TitleMatchResult) -> JobRelevanceResult:
    return JobRelevanceResult(
        decision="reject",
        score=0.0,
        summary=match.summary,
        matched_signals=match.matched_titles,
        concerns=["title gate"],
        source="title_gate",
        model_name=None,
        failure_cause=None,
        payload={
            "normalized_title": match.normalized_title,
            "matched_titles": match.matched_titles,
        },
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
