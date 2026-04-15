from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.accounts.models import Account
from app.domains.jobs.apply_target_candidate import ApplyTargetCandidate
from app.domains.jobs.models import ApplyTarget, Job, JobSighting
from app.domains.jobs.target_resolution import get_target_priority_values, refresh_preferred_apply_target
from app.domains.sources.models import JobSource


@dataclass(slots=True)
class DiscoveryCandidate:
    source_type: str
    company_name: str
    title: str
    listing_url: str
    external_job_id: str | None = None
    location: str | None = None
    apply_url: str | None = None
    apply_target_type: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    apply_targets: list[ApplyTargetCandidate] = field(default_factory=list)


_TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "ref", "referer", "referrer",
})


def strip_tracking_params(value: str | None) -> str | None:
    if not value:
        return value
    parsed = urlparse(value)
    clean_pairs = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS
    ]
    cleaned = parsed._replace(query=urlencode(clean_pairs), fragment="")
    return cleaned.geturl()


def normalize_text(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def normalize_url(value: str | None) -> str:
    if not value:
        return ""

    parsed = urlparse(value)
    scheme = (parsed.scheme or "https").lower()
    host = parsed.netloc.lower()
    path = _normalize_url_path(parsed.path)
    query_pairs = [
        (key.lower(), query_value)
        for key, query_value in parse_qsl(parsed.query, keep_blank_values=False)
        if key.lower() in {"gh_jid", "job", "jobid", "gh_src"}
    ]
    normalized_query = "&".join(f"{key}={query_value}" for key, query_value in sorted(query_pairs))
    return f"{scheme}://{host}{path}{('?' + normalized_query) if normalized_query else ''}"


def _normalize_url_path(path: str) -> str:
    segments = [segment for segment in path.split("/") if segment]
    default_path = path.rstrip("/") or "/"

    normalized_segments = _trim_noisy_url_segments(segments)
    if not normalized_segments:
        return default_path

    if len(normalized_segments) == 1:
        return f"/{normalized_segments[0]}"

    if len(normalized_segments) == 2:
        trailing_slash = "/" if _ends_with_apply_action(segments) else ""
        return f"/{normalized_segments[0]}/{normalized_segments[1]}{trailing_slash}"

    if _looks_like_job_identifier(normalized_segments[-1]):
        if len(normalized_segments) == 3 and _is_collection_segment(normalized_segments[1]):
            return f"/{'/'.join(normalized_segments)}"
        if _is_collection_segment(normalized_segments[0]):
            return f"/{normalized_segments[-1]}"
        return f"/{normalized_segments[-1]}"

    return default_path


def _trim_noisy_url_segments(segments: list[str]) -> list[str]:
    trimmed = segments[:]

    while trimmed and _is_locale_segment(trimmed[0]):
        trimmed = trimmed[1:]

    while len(trimmed) > 1 and _is_action_segment(trimmed[-1], previous=trimmed[-2]):
        trimmed = trimmed[:-1]

    while (
        len(trimmed) > 1
        and _is_collection_segment(trimmed[0])
        and _looks_like_job_identifier(trimmed[1])
    ):
        trimmed = trimmed[1:]

    return trimmed


def _is_locale_segment(segment: str) -> bool:
    return bool(re.fullmatch(r"[a-z]{2}(?:-[A-Za-z]{2})?", segment))


def _is_collection_segment(segment: str) -> bool:
    return segment.lower() in {"jobs", "job", "careers", "positions", "openings"}


def _is_action_segment(segment: str, *, previous: str) -> bool:
    lowered = segment.lower()
    if lowered in {"apply", "application"}:
        return True
    if lowered in {"job", "posting", "details", "description"}:
        return _looks_like_job_identifier(previous)
    return False


def _ends_with_apply_action(segments: list[str]) -> bool:
    return bool(segments) and segments[-1].lower() in {"apply"}


def _looks_like_job_identifier(segment: str) -> bool:
    if re.fullmatch(r"\d+", segment):
        return True
    if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f-]{27}", segment.lower()):
        return True
    return bool(re.search(r"(?:[_-][A-Za-z0-9]+)|(?:[A-Za-z]+[_-]\d+)|(?:\d{4,})", segment))


def build_canonical_key(candidate: DiscoveryCandidate) -> str:
    company = normalize_text(candidate.company_name).replace(" ", "-")
    title = normalize_text(candidate.title).replace(" ", "-")
    location = normalize_text(candidate.location).replace(" ", "-") or "unknown-location"
    return f"{company}-{title}-{location}"


def _find_job_by_destination_url(
    session: Session,
    account: Account,
    candidate: DiscoveryCandidate,
) -> Job | None:
    expected_url = normalize_url(candidate.apply_url or candidate.listing_url)
    if not expected_url:
        return None

    sightings = session.scalars(
        select(JobSighting).join(Job).where(Job.account_id == account.id),
    ).all()
    for sighting in sightings:
        sighting_url = sighting.normalized_url or normalize_url(sighting.apply_url or sighting.listing_url)
        if sighting_url == expected_url:
            return sighting.job
    return None


def _find_job_by_canonical_key(
    session: Session,
    account: Account,
    candidate: DiscoveryCandidate,
) -> Job | None:
    return session.scalar(
        select(Job).where(
            Job.account_id == account.id,
            Job.canonical_key == build_canonical_key(candidate),
        ),
    )


def resolve_existing_job(
    session: Session,
    account: Account,
    source: JobSource,
    candidate: DiscoveryCandidate,
) -> Job | None:
    return (
        _find_job_by_destination_url(session, account, candidate)
        or _find_job_by_canonical_key(session, account, candidate)
    )


def _upsert_sighting(
    session: Session,
    job: Job,
    source: JobSource,
    candidate: DiscoveryCandidate,
) -> None:
    normalized_candidate_url = normalize_url(candidate.apply_url or candidate.listing_url)
    existing_sighting = None
    if normalized_candidate_url:
        sightings = session.scalars(
            select(JobSighting).where(
                JobSighting.source_id == source.id,
                JobSighting.job_id == job.id,
            ),
        ).all()
        existing_sighting = next(
            (
                sighting
                for sighting in sightings
                if (sighting.normalized_url or normalize_url(sighting.apply_url or sighting.listing_url))
                == normalized_candidate_url
            ),
            None,
        )

    if not existing_sighting:
        existing_sighting = session.scalar(
            select(JobSighting).where(
                JobSighting.source_id == source.id,
                JobSighting.job_id == job.id,
                JobSighting.listing_url == candidate.listing_url,
            ),
        )

    if existing_sighting:
        existing_sighting.normalized_url = normalized_candidate_url
        existing_sighting.listing_url = strip_tracking_params(candidate.listing_url)
        existing_sighting.apply_url = strip_tracking_params(candidate.apply_url)
        existing_sighting.raw_payload = _compact_sighting_payload(candidate.raw_payload)
        existing_sighting.external_job_id = candidate.external_job_id
        return

    session.add(
        JobSighting(
            job=job,
            source=source,
            external_job_id=candidate.external_job_id,
            normalized_url=normalized_candidate_url,
            listing_url=strip_tracking_params(candidate.listing_url),
            apply_url=strip_tracking_params(candidate.apply_url),
            raw_payload=_compact_sighting_payload(candidate.raw_payload),
        ),
    )


def _upsert_apply_target(session: Session, job: Job, candidate: DiscoveryCandidate) -> None:
    target_candidates = list(candidate.apply_targets)
    if not target_candidates and candidate.apply_url and candidate.apply_target_type:
        target_candidates.append(
            ApplyTargetCandidate(
                destination_url=candidate.apply_url,
                target_type=candidate.apply_target_type,
                metadata=candidate.metadata,
            )
        )

    for target_candidate in target_candidates:
        if not target_candidate.destination_url or not target_candidate.target_type:
            continue

        existing_target = _find_existing_apply_target(job, target_candidate)
        if existing_target is not None:
            _merge_apply_target(existing_target, target_candidate)
            continue

        session.add(
            ApplyTarget(
                job=job,
                target_type=target_candidate.target_type,
                destination_url=strip_tracking_params(target_candidate.destination_url),
                metadata_json=target_candidate.metadata,
            ),
        )


def _find_existing_apply_target(job: Job, candidate: ApplyTargetCandidate) -> ApplyTarget | None:
    candidate_destination = normalize_url(candidate.destination_url)
    candidate_source = normalize_url(_target_source_url(candidate.metadata))
    candidate_resolved = normalize_url(_target_resolved_url(candidate.destination_url, candidate.metadata))

    for target in job.apply_targets:
        existing_destination = normalize_url(target.destination_url)
        existing_source = normalize_url(_target_source_url(target.metadata_json))
        existing_resolved = normalize_url(_target_resolved_url(target.destination_url, target.metadata_json))
        if candidate_destination and existing_destination == candidate_destination:
            return target
        if candidate_source and existing_source == candidate_source:
            return target
        if candidate_resolved and existing_resolved == candidate_resolved:
            return target
    return None


def _merge_apply_target(target: ApplyTarget, candidate: ApplyTargetCandidate) -> None:
    existing_priority = get_target_priority_values(
        destination_url=target.destination_url,
        target_type=target.target_type,
        metadata=target.metadata_json,
    )
    candidate_priority = get_target_priority_values(
        destination_url=candidate.destination_url,
        target_type=candidate.target_type,
        metadata=candidate.metadata,
    )

    if candidate_priority >= existing_priority:
        target.target_type = candidate.target_type
        target.destination_url = strip_tracking_params(candidate.destination_url)

    target.metadata_json = _merge_target_metadata(target.metadata_json, candidate.metadata)


def _merge_target_metadata(existing: dict[str, Any] | None, new: dict[str, Any] | None) -> dict[str, Any]:
    existing = dict(existing or {})
    new = dict(new or {})
    merged: dict[str, Any] = {**existing, **new}
    source_url = _first_string(existing.get("source_url"), new.get("source_url"))
    if source_url:
        merged["source_url"] = source_url
    else:
        merged.pop("source_url", None)

    merged.pop("source_urls", None)
    merged.pop("provenance_links", None)
    merged.pop("compatibility_notes", None)
    return merged


def _first_string(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str):
            candidate = value.strip()
            if candidate:
                return candidate
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip():
                    return item.strip()
    return None


def _compact_sighting_payload(raw_payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(raw_payload, dict):
        return {}
    compacted = dict(raw_payload)
    compacted.pop("outbound_links", None)
    return compacted


def _target_source_url(metadata: dict[str, Any] | None) -> str | None:
    if not isinstance(metadata, dict):
        return None
    source_url = metadata.get("source_url")
    if isinstance(source_url, str) and source_url.strip():
        return source_url
    return None


def _target_resolved_url(destination_url: str, metadata: dict[str, Any] | None) -> str:
    if isinstance(metadata, dict):
        resolved = metadata.get("resolved_destination_url")
        if isinstance(resolved, str) and resolved.strip():
            return resolved
    return destination_url


def ingest_candidate(
    session: Session,
    account: Account,
    source: JobSource,
    candidate: DiscoveryCandidate,
) -> tuple[Job, bool]:
    job = resolve_existing_job(session, account, source, candidate)
    created = False

    if not job:
        job = Job(
            account_id=account.id,
            canonical_key=build_canonical_key(candidate),
            company_name=candidate.company_name,
            title=candidate.title,
            location=candidate.location,
            status="discovered",
        )
        session.add(job)
        session.flush()
        created = True
    else:
        job.company_name = candidate.company_name
        job.title = candidate.title
        job.location = candidate.location

    _upsert_sighting(session, job, source, candidate)
    session.flush()
    _upsert_apply_target(session, job, candidate)
    session.flush()
    refresh_preferred_apply_target(job)
    return job, created
