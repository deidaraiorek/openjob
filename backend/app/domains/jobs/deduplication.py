from __future__ import annotations

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
    path = parsed.path.rstrip("/")
    query_pairs = [
        (key.lower(), query_value)
        for key, query_value in parse_qsl(parsed.query, keep_blank_values=False)
        if key.lower() in {"gh_jid", "job", "jobid", "gh_src"}
    ]
    normalized_query = "&".join(f"{key}={query_value}" for key, query_value in sorted(query_pairs))
    return f"{parsed.netloc.lower()}{path}{('?' + normalized_query) if normalized_query else ''}"


def build_canonical_key(candidate: DiscoveryCandidate) -> str:
    company = normalize_text(candidate.company_name).replace(" ", "-")
    title = normalize_text(candidate.title).replace(" ", "-")
    location = normalize_text(candidate.location).replace(" ", "-") or "unknown-location"
    return f"{company}-{title}-{location}"


def _find_job_by_external_id(
    session: Session,
    source: JobSource,
    candidate: DiscoveryCandidate,
) -> Job | None:
    if not candidate.external_job_id:
        return None

    sighting = session.scalar(
        select(JobSighting).where(
            JobSighting.source_id == source.id,
            JobSighting.external_job_id == candidate.external_job_id,
        ),
    )
    return sighting.job if sighting else None


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
        if normalize_url(sighting.apply_url or sighting.listing_url) == expected_url:
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
        _find_job_by_external_id(session, source, candidate)
        or _find_job_by_destination_url(session, account, candidate)
        or _find_job_by_canonical_key(session, account, candidate)
    )


def _upsert_sighting(
    session: Session,
    job: Job,
    source: JobSource,
    candidate: DiscoveryCandidate,
) -> None:
    existing_sighting = None
    if candidate.external_job_id:
        existing_sighting = session.scalar(
            select(JobSighting).where(
                JobSighting.source_id == source.id,
                JobSighting.external_job_id == candidate.external_job_id,
            ),
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
        existing_sighting.apply_url = candidate.apply_url
        existing_sighting.raw_payload = candidate.raw_payload
        return

    session.add(
        JobSighting(
            job=job,
            source=source,
            external_job_id=candidate.external_job_id,
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
