from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.config import get_settings
from app.domains.accounts.service import ensure_account
from app.domains.jobs.deduplication import DiscoveryCandidate, ingest_candidate, resolve_existing_job
from app.domains.jobs.relevance import (
    cached_relevance_for_job,
    delete_relevance_task,
    mark_job_pending,
    upsert_relevance_task,
)
from app.domains.jobs.models import Job, JobRelevanceTask
from app.domains.role_profiles.models import RoleProfile
from app.domains.sources.models import JobSource
from app.domains.sources.link_resolution import resolve_github_candidates, summarize_candidate_targets
from app.domains.sources.sync_control import (
    acquire_source_sync_lease,
    mark_source_synced,
    release_source_sync_lease,
    select_due_source_ids,
)
from app.domains.sources.url_normalization import (
    derive_ashby_organization_host_token,
    derive_greenhouse_board_token,
    derive_lever_company_slug,
    derive_smartrecruiters_company_identifier,
    resolve_github_raw_url,
)
from app.db.session import get_session_factory
from app.integrations.ashby.client import fetch_job_postings as fetch_ashby_postings
from app.integrations.ashby.client import parse_postings as parse_ashby_postings
from app.integrations.github_curated.client import fetch_markdown
from app.integrations.github_curated.parser import parse_markdown_jobs
from app.integrations.greenhouse.client import fetch_jobs as fetch_greenhouse_jobs
from app.integrations.greenhouse.client import parse_jobs as parse_greenhouse_jobs
from app.integrations.lever.client import fetch_postings as fetch_lever_postings
from app.integrations.lever.client import parse_postings as parse_lever_postings
from app.integrations.linkedin.discovery import parse_search_results as parse_linkedin_search_results
from app.integrations.smartrecruiters.client import fetch_postings as fetch_smartrecruiters_postings
from app.integrations.smartrecruiters.client import parse_postings as parse_smartrecruiters_postings
from app.integrations.test_jobboard.client import fetch_jobs as fetch_test_jobboard_jobs
from app.integrations.test_jobboard.client import parse_jobs as parse_test_jobboard_jobs
from app.tasks.job_relevance import drain_relevance_tasks_for_account, drain_relevance_tasks_now
from app.domains.logs.service import log_system_event
HARD_REJECT_SCORE_THRESHOLD = 0.15


def empty_sync_summary() -> dict[str, int]:
    return {
        "processed": 0,
        "created": 0,
        "updated": 0,
        "pending_title_screening": 0,
        "pending_full_relevance": 0,
        "api_compatible_targets": 0,
        "browser_compatible_targets": 0,
        "manual_only_targets": 0,
        "resolution_failed_targets": 0,
    }


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
        markdown = raw_payload if raw_payload is not None else fetch_markdown(
            resolve_github_raw_url(source))
        return resolve_github_candidates(
            parse_markdown_jobs(markdown),
            settings=source.settings_json,
        )

    if source.source_type == "greenhouse_board":
        board_token = derive_greenhouse_board_token(source)
        payload = raw_payload if raw_payload is not None else fetch_greenhouse_jobs(
            board_token)
        return parse_greenhouse_jobs(
            payload,
            board_token=board_token,
            api_key=source.settings_json.get("api_key"),
        )

    if source.source_type == "lever_postings":
        company_slug = derive_lever_company_slug(source)
        payload = raw_payload if raw_payload is not None else fetch_lever_postings(
            company_slug)
        return parse_lever_postings(
            payload,
            company_slug=company_slug,
            company_name=source.settings_json.get("company_name"),
            api_key=source.settings_json.get("api_key"),
        )

    if source.source_type == "ashby_board":
        organization_host_token = derive_ashby_organization_host_token(source)
        payload = raw_payload if raw_payload is not None else fetch_ashby_postings(
            organization_host_token)
        return parse_ashby_postings(
            payload,
            organization_host_token=organization_host_token,
            company_name=source.settings_json.get("company_name"),
        )

    if source.source_type == "smartrecruiters_board":
        company_identifier = derive_smartrecruiters_company_identifier(source)
        payload = raw_payload if raw_payload is not None else fetch_smartrecruiters_postings(
            company_identifier)
        return parse_smartrecruiters_postings(
            payload,
            company_identifier=company_identifier,
            company_name=source.settings_json.get("company_name"),
        )

    if source.source_type == "linkedin_search":
        if raw_payload is None:
            raise ValueError(
                "LinkedIn discovery requires a browser-captured payload")
        return parse_linkedin_search_results(raw_payload)

    if source.source_type == "test_jobboard":
        base_url = source.base_url or "http://localhost:4000"
        jobs = raw_payload if raw_payload is not None else fetch_test_jobboard_jobs(base_url)
        return parse_test_jobboard_jobs(
            jobs,
            base_url=base_url,
            company_name=source.settings_json.get("company_name", "NovaCorp"),
        )

    raise ValueError(f"Unsupported source type: {source.source_type}")


def _requeue_system_fallback_reviews(session: Session, *, account_id: int) -> int:
    from sqlalchemy.orm import selectinload as _selectinload
    jobs = session.scalars(
        select(Job)
        .where(
            Job.account_id == account_id,
            Job.relevance_decision == "review",
            Job.relevance_source == "system_fallback",
        )
        .options(_selectinload(Job.relevance_tasks))
    ).all()

    requeued = 0
    for job in jobs:
        if any(t.phase == "title_screening" for t in job.relevance_tasks):
            continue
        mark_job_pending(job, phase="title_screening")
        upsert_relevance_task(
            session,
            account_id=account_id,
            job_id=job.id,
            phase="title_screening",
            reset_attempts=True,
        )
        requeued += 1
    return requeued


def sync_source(session: Session, source_id: int, raw_payload: Any = None) -> dict[str, int]:
    settings = get_settings()
    source = session.get(JobSource, source_id)
    if not source:
        raise ValueError(f"Unknown source: {source_id}")
    if not source.active:
        return empty_sync_summary()

    account = ensure_account(
        session, source.account.email if source.account else "owner@example.com")
    profile = _load_role_profile(session, source)
    candidates = load_candidates(source, raw_payload=raw_payload)
    compatibility_summary = summarize_candidate_targets(candidates)
    touched_job_ids: list[int] = []

    processed = 0
    created = 0
    updated = 0

    for candidate in candidates:
        processed += 1
        existing_job = resolve_existing_job(
            session, account, source, candidate)
        cached_result = None
        if existing_job is not None:
            cached_result = cached_relevance_for_job(
                profile,
                existing_job,
                source_type=candidate.source_type,
                apply_target_type=candidate.apply_target_type,
                description_snippet=(
                    " ".join(candidate.raw_payload.get(
                        "description", "").strip().split())
                    if isinstance(candidate.raw_payload.get("description"), str)
                    else None
                ),
            )
        result = cached_result
        if result is not None and _is_hard_reject(result):
            if existing_job is not None and _should_auto_prune(existing_job):
                session.delete(existing_job)
            continue

        job, was_created = ingest_candidate(
            session, account, source, candidate)
        touched_job_ids.append(job.id)
        if cached_result is None:
            if not profile or not profile.prompt.strip():
                job.relevance_decision = "match"
                job.relevance_source = "system_fallback"
                job.relevance_score = 1.0
                job.relevance_summary = "No role profile configured, so the job stays visible by default."
            else:
                for task in list(job.relevance_tasks):
                    delete_relevance_task(session, task)
                mark_job_pending(job, phase="title_screening")
                upsert_relevance_task(
                    session,
                    account_id=account.id,
                    job_id=job.id,
                    phase="title_screening",
                    reset_attempts=True,
                )
        else:
            for task in list(job.relevance_tasks):
                delete_relevance_task(session, task)
            job.relevance_decision = cached_result.decision
            job.relevance_source = cached_result.source
            job.relevance_score = cached_result.score
            job.relevance_summary = cached_result.summary
        if was_created:
            created += 1
        else:
            updated += 1

    session.commit()

    if profile and profile.prompt.strip():
        _requeue_system_fallback_reviews(session, account_id=account.id)
        session.commit()
        drain_relevance_tasks_now(
            session,
            account_id=account.id,
            title_batch_limit=settings.inline_title_screening_batch_limit,
            full_batch_limit=0,
        )

    pending_title_screening = session.scalar(
        select(func.count(JobRelevanceTask.id)).where(
            JobRelevanceTask.account_id == account.id,
            JobRelevanceTask.job_id.in_(
                touched_job_ids if touched_job_ids else [-1]),
            JobRelevanceTask.phase == "title_screening",
        )
    ) or 0
    pending_full_relevance = session.scalar(
        select(func.count(JobRelevanceTask.id)).where(
            JobRelevanceTask.account_id == account.id,
            JobRelevanceTask.job_id.in_(
                touched_job_ids if touched_job_ids else [-1]),
            JobRelevanceTask.phase == "full_relevance",
        )
    ) or 0
    summary = {
        "processed": processed,
        "created": created,
        "updated": updated,
        "pending_title_screening": pending_title_screening,
        "pending_full_relevance": pending_full_relevance,
        **compatibility_summary,
    }
    source.last_sync_summary_json = summary
    session.flush()
    return summary


def sync_all_sources_now() -> list[dict[str, int]]:
    session_factory = get_session_factory()
    with session_factory() as session:
        source_ids = session.scalars(
            select(JobSource.id).where(JobSource.active.is_(True))).all()
        return [sync_source(session, source_id) for source_id in source_ids]


def enqueue_due_source_syncs_now(session: Session) -> int:
    due_source_ids = select_due_source_ids(session)
    for source_id in due_source_ids:
        sync_source_task.delay(source_id)
    return len(due_source_ids)


@celery_app.task(name="app.tasks.discovery.sync_source")
def sync_source_task(source_id: int) -> dict[str, int]:
    session_factory = get_session_factory()
    with session_factory() as session:
        source = session.get(JobSource, source_id)
        if not source or not source.active:
            return empty_sync_summary()

        if not acquire_source_sync_lease(session, source_id=source_id):
            session.rollback()
            return empty_sync_summary()
        session.commit()

        try:
            log_system_event(
                session,
                event_type="source_sync_started",
                source="discovery",
                account_id=source.account_id,
                payload={"source_id": source_id, "source_type": source.source_type, "source_name": source.name},
            )
            session.commit()
            summary = sync_source(session, source_id)
            source.last_sync_summary_json = summary
            mark_source_synced(source)
            log_system_event(
                session,
                event_type="source_sync_completed",
                source="discovery",
                account_id=source.account_id,
                payload={"source_id": source_id, "source_type": source.source_type, "source_name": source.name, **summary},
            )
            session.commit()
        except Exception as exc:
            with session_factory() as err_session:
                err_source = err_session.get(JobSource, source_id)
                log_system_event(
                    err_session,
                    event_type="source_sync_failed",
                    source="discovery",
                    account_id=err_source.account_id if err_source else None,
                    payload={"source_id": source_id, "error": str(exc)},
                )
                release_source_sync_lease(err_session, source_id=source_id)
                err_session.commit()
            raise

        if summary["pending_title_screening"] or summary["pending_full_relevance"]:
            drain_relevance_tasks_for_account(source.account_id)
        return summary


@celery_app.task(name="app.tasks.discovery.sync_all_sources")
def sync_all_sources() -> list[dict[str, int]]:
    return sync_all_sources_now()


@celery_app.task(name="app.tasks.discovery.enqueue_due_source_syncs")
def enqueue_due_source_syncs() -> int:
    session_factory = get_session_factory()
    with session_factory() as session:
        return enqueue_due_source_syncs_now(session)
