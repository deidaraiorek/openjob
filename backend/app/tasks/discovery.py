from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.config import get_settings
from app.domains.accounts.service import ensure_account
from app.domains.jobs.deduplication import DiscoveryCandidate, ingest_candidate, resolve_existing_job
from app.domains.jobs.relevance import (
    apply_relevance_result,
    cached_relevance_for_job,
    queued_relevance_result,
    screen_candidate_titles,
    title_screen_reject_result,
)
from app.domains.jobs.models import Job
from app.domains.role_profiles.models import RoleProfile
from app.domains.sources.models import JobSource
from app.domains.sources.url_normalization import (
    derive_greenhouse_board_token,
    derive_lever_company_slug,
    resolve_github_raw_url,
)
from app.db.session import get_session_factory
from app.integrations.github_curated.client import fetch_markdown
from app.integrations.github_curated.parser import parse_markdown_jobs
from app.integrations.greenhouse.client import fetch_jobs as fetch_greenhouse_jobs
from app.integrations.greenhouse.client import parse_jobs as parse_greenhouse_jobs
from app.integrations.lever.client import fetch_postings as fetch_lever_postings
from app.integrations.lever.client import parse_postings as parse_lever_postings
from app.integrations.linkedin.discovery import parse_search_results as parse_linkedin_search_results
from app.tasks.job_relevance import evaluate_job_batch_now
HARD_REJECT_SCORE_THRESHOLD = 0.15


def _is_hard_reject(result) -> bool:
    return (
        result.source == "ai"
        and result.decision == "reject"
        and result.score is not None
        and result.score <= HARD_REJECT_SCORE_THRESHOLD
    )


def _should_auto_prune(job: Job) -> bool:
    return (
        job.relevance_source == "ai"
        and job.relevance_decision == "reject"
        and job.relevance_score is not None
        and job.relevance_score <= HARD_REJECT_SCORE_THRESHOLD
        and not job.application_runs
        and not job.question_tasks
    )


def _load_role_profile(session: Session, source: JobSource) -> RoleProfile | None:
    return session.scalar(
        select(RoleProfile).where(RoleProfile.account_id == source.account_id),
    )


def load_candidates(source: JobSource, raw_payload: Any = None) -> list[DiscoveryCandidate]:
    if source.source_type == "github_curated":
        markdown = raw_payload if raw_payload is not None else fetch_markdown(resolve_github_raw_url(source))
        return parse_markdown_jobs(markdown)

    if source.source_type == "greenhouse_board":
        board_token = derive_greenhouse_board_token(source)
        payload = raw_payload if raw_payload is not None else fetch_greenhouse_jobs(board_token)
        return parse_greenhouse_jobs(
            payload,
            board_token=board_token,
            api_key=source.settings_json.get("api_key"),
        )

    if source.source_type == "lever_postings":
        company_slug = derive_lever_company_slug(source)
        payload = raw_payload if raw_payload is not None else fetch_lever_postings(company_slug)
        return parse_lever_postings(
            payload,
            company_slug=company_slug,
            company_name=source.settings_json.get("company_name"),
            api_key=source.settings_json.get("api_key"),
        )

    if source.source_type == "linkedin_search":
        if raw_payload is None:
            raise ValueError("LinkedIn discovery requires a browser-captured payload")
        return parse_linkedin_search_results(raw_payload)

    raise ValueError(f"Unsupported source type: {source.source_type}")


def sync_source(session: Session, source_id: int, raw_payload: Any = None) -> dict[str, int]:
    source = session.get(JobSource, source_id)
    if not source:
        raise ValueError(f"Unknown source: {source_id}")
    if not source.active:
        return {"processed": 0, "created": 0, "updated": 0}

    account = ensure_account(session, session.get(JobSource, source_id).account.email if source.account else "owner@example.com")
    profile = _load_role_profile(session, source)
    candidates = load_candidates(source, raw_payload=raw_payload)
    screened_titles = screen_candidate_titles(profile, candidates)
    queued_job_ids: list[int] = []

    processed = 0
    created = 0
    updated = 0

    for candidate in candidates:
        processed += 1
        existing_job = resolve_existing_job(session, account, source, candidate)
        cached_result = None
        if existing_job is not None:
            cached_result = cached_relevance_for_job(
                profile,
                existing_job,
                source_type=candidate.source_type,
                apply_target_type=candidate.apply_target_type,
                description_snippet=(
                    " ".join(candidate.raw_payload.get("description", "").strip().split())[:800]
                    if isinstance(candidate.raw_payload.get("description"), str)
                    else None
                ),
            )
        screening = screened_titles.get(candidate.title)
        result = cached_result
        if result is not None and _is_hard_reject(result):
            if existing_job is not None and _should_auto_prune(existing_job):
                session.delete(existing_job)
            continue

        job, was_created = ingest_candidate(session, account, source, candidate)
        if cached_result is None:
            if screening is None:
                raise ValueError(f"Missing title screening result for candidate: {candidate.title}")
            if screening.decision == "reject":
                result = title_screen_reject_result(candidate.title, screening)
            else:
                result = queued_relevance_result(
                    candidate.title,
                    screening,
                    summary="Title passed screening and is queued for deeper AI relevance review.",
                    failure_cause="queued_for_async_relevance",
                )
                queued_job_ids.append(job.id)
            apply_relevance_result(
                session,
                account_id=account.id,
                job=job,
                result=result,
                profile=profile,
            )
        else:
            job.relevance_decision = cached_result.decision
            job.relevance_source = cached_result.source
            job.relevance_score = cached_result.score
            job.relevance_summary = cached_result.summary
        if was_created:
            created += 1
        else:
            updated += 1

    session.commit()
    if queued_job_ids:
        evaluate_job_batch_now(session, account_id=account.id, job_ids=queued_job_ids)
    return {"processed": processed, "created": created, "updated": updated}


def sync_all_sources_now() -> list[dict[str, int]]:
    session_factory = get_session_factory()
    with session_factory() as session:
        source_ids = session.scalars(select(JobSource.id).where(JobSource.active.is_(True))).all()
        return [sync_source(session, source_id) for source_id in source_ids]


@celery_app.task(name="app.tasks.discovery.sync_source")
def sync_source_task(source_id: int) -> dict[str, int]:
    session_factory = get_session_factory()
    with session_factory() as session:
        return sync_source(session, source_id)


@celery_app.task(name="app.tasks.discovery.sync_all_sources")
def sync_all_sources() -> list[dict[str, int]]:
    return sync_all_sources_now()
