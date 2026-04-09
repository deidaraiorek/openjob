from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.accounts.models import Account
from app.domains.jobs.models import ApplyTarget, Job, JobSighting
from app.domains.jobs.target_resolution import refresh_preferred_apply_target
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
        existing_sighting.listing_url = candidate.listing_url
        existing_sighting.apply_url = candidate.apply_url
        existing_sighting.raw_payload = candidate.raw_payload
        existing_sighting.external_job_id = candidate.external_job_id
        return

    session.add(
        JobSighting(
            job=job,
            source=source,
            external_job_id=candidate.external_job_id,
            normalized_url=normalized_candidate_url,
            listing_url=candidate.listing_url,
            apply_url=candidate.apply_url,
            raw_payload=candidate.raw_payload,
        ),
    )


def _upsert_apply_target(session: Session, job: Job, candidate: DiscoveryCandidate) -> None:
    if not candidate.apply_url or not candidate.apply_target_type:
        return

    for target in job.apply_targets:
        if (
            target.destination_url == candidate.apply_url
            and target.target_type == candidate.apply_target_type
        ):
            target.metadata_json = candidate.metadata
            return

    session.add(
        ApplyTarget(
            job=job,
            target_type=candidate.apply_target_type,
            destination_url=candidate.apply_url,
            metadata_json=candidate.metadata,
        ),
    )


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
