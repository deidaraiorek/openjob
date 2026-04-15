from __future__ import annotations

from datetime import UTC, datetime, timedelta
import time

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.celery_app import celery_app
from app.config import get_settings
from app.domains.jobs.models import Job, JobRelevanceTask, JobSighting
from app.domains.jobs.relevance_policy import build_decision_policy, derive_profile_hints
from app.domains.jobs.relevance import (
    apply_relevance_result,
    build_batch_request_for_job,
    delete_relevance_task,
    evaluate_job_relevance,
    is_transient_failure_cause,
    mark_job_pending,
    pending_summary_for_phase,
    screening_payload_for_task,
    title_screen_reject_result,
    upsert_relevance_task,
    TitleGateResult,
)
from app.domains.role_profiles.models import RoleProfile
from app.db.session import get_session_factory
from app.integrations.openai.job_relevance import classify_job_relevance_batch
from app.integrations.openai.job_title_screening import classify_job_titles


def rescore_job(session: Session, *, account_id: int, job_id: int) -> Job | None:
    job = session.scalar(
        select(Job)
        .where(Job.id == job_id, Job.account_id == account_id)
        .options(
            selectinload(Job.sightings).selectinload(JobSighting.source),
            selectinload(Job.apply_targets),
        ),
    )
    if not job:
        return None

    profile = session.scalar(
        select(RoleProfile).where(RoleProfile.account_id == account_id),
    )
    result = evaluate_job_relevance(profile, job)
    apply_relevance_result(
        session,
        account_id=account_id,
        job=job,
        result=result,
        profile=profile,
    )
    for task in list(job.relevance_tasks):
        session.delete(task)
    session.flush()
    return job


def rescore_account_jobs_now(session: Session, *, account_id: int) -> int:
    job_ids = session.scalars(
        select(Job.id).where(Job.account_id == account_id),
    ).all()

    rescored = 0
    for job_id in job_ids:
        if rescore_job(session, account_id=account_id, job_id=job_id) is not None:
            rescored += 1

    session.commit()
    return rescored


def _lease_ready_tasks(
    session: Session,
    *,
    account_id: int,
    phase: str,
    limit: int,
) -> list[JobRelevanceTask]:
    if limit <= 0:
        return []

    settings = get_settings()
    now = datetime.now(UTC)
    lease_expires_at = now + timedelta(seconds=max(1, settings.relevance_task_lease_seconds))
    tasks = session.scalars(
        select(JobRelevanceTask)
        .where(
            JobRelevanceTask.account_id == account_id,
            JobRelevanceTask.phase == phase,
            JobRelevanceTask.available_at <= now,
            (JobRelevanceTask.lease_expires_at.is_(None) | (JobRelevanceTask.lease_expires_at <= now)),
        )
        .options(
            selectinload(JobRelevanceTask.job).selectinload(Job.sightings).selectinload(JobSighting.source),
            selectinload(JobRelevanceTask.job).selectinload(Job.apply_targets),
            selectinload(JobRelevanceTask.job).selectinload(Job.relevance_evaluations),
            selectinload(JobRelevanceTask.job).selectinload(Job.relevance_tasks),
        )
        .order_by(JobRelevanceTask.available_at.asc(), JobRelevanceTask.id.asc())
        .limit(limit)
    ).all()
    for task in tasks:
        task.lease_expires_at = lease_expires_at
    session.flush()
    return tasks


def _next_retry_time(*, attempt_count: int) -> datetime:
    settings = get_settings()
    base_delay = max(0.5, float(settings.relevance_retry_base_delay_seconds))
    return datetime.now(UTC) + timedelta(seconds=base_delay * (2 ** min(max(0, attempt_count - 1), 6)))


def _handle_pending_task_failure(
    session: Session,
    *,
    account_id: int,
    task: JobRelevanceTask,
    failure_cause: str | None,
    summary: str,
) -> bool:
    settings = get_settings()
    task.attempt_count += 1
    task.last_failure_cause = failure_cause
    task.lease_expires_at = None

    if is_transient_failure_cause(failure_cause):
        task.available_at = _next_retry_time(attempt_count=task.attempt_count)
        mark_job_pending(task.job, phase=task.phase, summary=pending_summary_for_phase(task.phase))
        session.flush()
        return False

    if failure_cause == "provider_response_invalid":
        task.available_at = _next_retry_time(attempt_count=task.attempt_count)
        mark_job_pending(task.job, phase=task.phase, summary=pending_summary_for_phase(task.phase))
        session.flush()
        return False

    from app.integrations.openai.job_relevance import JobRelevanceResult

    apply_relevance_result(
        session,
        account_id=account_id,
        job=task.job,
        result=JobRelevanceResult(
            decision="review",
            score=None,
            summary=summary,
            matched_signals=[],
            concerns=[failure_cause or "provider_unavailable"],
            source="system_fallback",
            model_name=None,
            failure_cause=failure_cause,
            payload={"decision_rationale_type": "provider_fallback"},
        ),
        profile=session.scalar(select(RoleProfile).where(RoleProfile.account_id == account_id)),
    )
    delete_relevance_task(session, task)
    return True


def _process_title_screening_tasks(
    session: Session,
    *,
    account_id: int,
    batch_limit: int,
) -> int:
    settings = get_settings()
    profile = session.scalar(select(RoleProfile).where(RoleProfile.account_id == account_id))
    task_limit = max(0, batch_limit) * max(1, settings.title_screening_batch_size)
    tasks = _lease_ready_tasks(session, account_id=account_id, phase="title_screening", limit=task_limit)
    if not tasks:
        return 0

    tasks = [task for task in tasks if task.job is not None]
    if not tasks:
        return 0

    processed = 0
    for index in range(0, len(tasks), settings.title_screening_batch_size):
        chunk = tasks[index: index + settings.title_screening_batch_size]
        result = classify_job_titles(
            profile.prompt if profile else None,
            [task.job.title for task in chunk],
            decision_policy=build_decision_policy(profile),
            derived_profile_hints=derive_profile_hints(profile),
            settings=settings,
        )
        for task, item in zip(chunk, result.items, strict=False):
            processed += 1
            if item.source != "ai":
                _handle_pending_task_failure(
                    session,
                    account_id=account_id,
                    task=task,
                    failure_cause=item.failure_cause,
                    summary="AI title screening could not complete repeatedly, so this job needs review.",
                )
                continue

            screening = TitleGateResult(
                title=item.title,
                decision=item.decision,
                summary=item.summary,
                source=item.source,
                model_name=item.model_name,
                failure_cause=item.failure_cause,
                payload={**result.payload, **item.payload, "decision_rationale_type": item.decision_rationale_type},
            )
            if screening.decision == "reject":
                apply_relevance_result(
                    session,
                    account_id=account_id,
                    job=task.job,
                    result=title_screen_reject_result(task.job.title, screening),
                    profile=profile,
                )
                delete_relevance_task(session, task)
                continue

            mark_job_pending(task.job, phase="full_relevance")
            upsert_relevance_task(
                session,
                account_id=account_id,
                job_id=task.job.id,
                phase="full_relevance",
                payload=screening_payload_for_task(screening),
                reset_attempts=True,
            )
            delete_relevance_task(session, task)
        session.commit()
        batch_delay = getattr(settings, "title_screening_batch_delay_seconds", 0.0)
        if batch_delay and index + settings.title_screening_batch_size < len(tasks):
            time.sleep(max(0.0, batch_delay))

    return processed


def _process_full_relevance_tasks(
    session: Session,
    *,
    account_id: int,
    batch_limit: int,
) -> int:
    settings = get_settings()
    profile = session.scalar(select(RoleProfile).where(RoleProfile.account_id == account_id))
    task_limit = max(0, batch_limit) * max(1, settings.full_relevance_batch_size)
    tasks = _lease_ready_tasks(session, account_id=account_id, phase="full_relevance", limit=task_limit)
    tasks = [task for task in tasks if task.job is not None]
    if not tasks:
        return 0

    processed = 0
    for index in range(0, len(tasks), settings.full_relevance_batch_size):
        chunk = tasks[index: index + settings.full_relevance_batch_size]
        results = classify_job_relevance_batch(
            profile,
            [build_batch_request_for_job(task.job, profile=profile, screening_payload=task.payload) for task in chunk],
            decision_policy=build_decision_policy(profile),
            derived_profile_hints=derive_profile_hints(profile),
            settings=settings,
        )
        for task, result in zip(chunk, results, strict=False):
            processed += 1
            if result.source != "ai":
                _handle_pending_task_failure(
                    session,
                    account_id=account_id,
                    task=task,
                    failure_cause=result.failure_cause,
                    summary="AI relevance classification could not complete repeatedly, so this job needs review.",
                )
                continue

            apply_relevance_result(
                session,
                account_id=account_id,
                job=task.job,
                result=result,
                profile=profile,
            )
            delete_relevance_task(session, task)
        session.commit()
        if settings.full_relevance_batch_delay_seconds and index + settings.full_relevance_batch_size < len(tasks):
            time.sleep(max(0.0, settings.full_relevance_batch_delay_seconds))

    return processed


def ready_relevance_task_count(session: Session, *, account_id: int | None = None) -> int:
    now = datetime.now(UTC)
    stmt = select(func.count(JobRelevanceTask.id))
    if account_id is not None:
        stmt = stmt.where(JobRelevanceTask.account_id == account_id)
    return session.scalar(
        stmt.where(
            JobRelevanceTask.available_at <= now,
            (JobRelevanceTask.lease_expires_at.is_(None) | (JobRelevanceTask.lease_expires_at <= now)),
        )
    ) or 0


def outstanding_relevance_task_count(session: Session, *, account_id: int | None = None) -> int:
    stmt = select(func.count(JobRelevanceTask.id))
    if account_id is not None:
        stmt = stmt.where(JobRelevanceTask.account_id == account_id)
    return session.scalar(stmt) or 0


def next_relevance_task_available_at(session: Session, *, account_id: int | None = None) -> datetime | None:
    stmt = select(func.min(JobRelevanceTask.available_at))
    if account_id is not None:
        stmt = stmt.where(JobRelevanceTask.account_id == account_id)
    return session.scalar(stmt)


def drain_relevance_tasks_now(
    session: Session,
    *,
    account_id: int,
    title_batch_limit: int,
    full_batch_limit: int,
) -> dict[str, int]:
    title_processed = _process_title_screening_tasks(
        session,
        account_id=account_id,
        batch_limit=title_batch_limit,
    )
    full_processed = _process_full_relevance_tasks(
        session,
        account_id=account_id,
        batch_limit=full_batch_limit,
    )
    return {
        "title_screening_processed": title_processed,
        "full_relevance_processed": full_processed,
    }


def drain_relevance_tasks_for_account(account_id: int) -> int:
    session_factory = get_session_factory()
    settings = get_settings()
    total_processed = 0
    while True:
        with session_factory() as session:
            summary = drain_relevance_tasks_now(
                session,
                account_id=account_id,
                title_batch_limit=settings.background_relevance_batch_limit,
                full_batch_limit=settings.background_relevance_batch_limit,
            )
            total_processed += summary["title_screening_processed"] + summary["full_relevance_processed"]
            ready_count = ready_relevance_task_count(session, account_id=account_id)
            outstanding_count = outstanding_relevance_task_count(session, account_id=account_id)
            next_available_at = next_relevance_task_available_at(session, account_id=account_id)
        if ready_count > 0:
            time.sleep(0.1)
            continue
        if outstanding_count == 0:
            break
        if next_available_at is None:
            break
        aware_next = next_available_at.replace(tzinfo=UTC) if next_available_at.tzinfo is None else next_available_at
        wait_seconds = max(0.1, min(5.0, (aware_next - datetime.now(UTC)).total_seconds()))
        time.sleep(wait_seconds)
    return total_processed


def drain_all_relevance_tasks() -> int:
    session_factory = get_session_factory()
    with session_factory() as session:
        account_ids = session.scalars(select(JobRelevanceTask.account_id).distinct()).all()

    processed = 0
    for account_id in account_ids:
        processed += drain_relevance_tasks_for_account(account_id)
    return processed


def evaluate_job_batch_now(session: Session, *, account_id: int, job_ids: list[int]) -> int:
    if not job_ids:
        return 0

    jobs = session.scalars(
        select(Job)
        .where(Job.account_id == account_id, Job.id.in_(job_ids))
        .options(
            selectinload(Job.sightings).selectinload(JobSighting.source),
            selectinload(Job.apply_targets),
            selectinload(Job.relevance_evaluations),
        )
        .order_by(Job.id.asc()),
    ).all()
    if not jobs:
        return 0

    profile = session.scalar(
        select(RoleProfile).where(RoleProfile.account_id == account_id),
    )
    settings = get_settings()
    batch_size = max(1, settings.full_relevance_batch_size)
    batch_delay_seconds = max(0.0, settings.full_relevance_batch_delay_seconds)
    processed = 0

    for index in range(0, len(jobs), batch_size):
        chunk = jobs[index: index + batch_size]
        requests = [build_batch_request_for_job(job, profile=profile) for job in chunk]
        results = classify_job_relevance_batch(
            profile,
            requests,
            decision_policy=build_decision_policy(profile),
            derived_profile_hints=derive_profile_hints(profile),
            settings=settings,
        )
        for job, result in zip(chunk, results, strict=False):
            apply_relevance_result(
                session,
                account_id=account_id,
                job=job,
                result=result,
                profile=profile,
            )
            processed += 1
        session.commit()
        if batch_delay_seconds and index + batch_size < len(jobs):
            time.sleep(batch_delay_seconds)

    return processed


def queue_job_relevance_batch(account_id: int, job_ids: list[int]) -> bool:
    if not job_ids:
        return False

    try:
        evaluate_job_batch_task.delay(account_id=account_id, job_ids=job_ids)
    except Exception:
        return False
    return True


@celery_app.task(name="app.tasks.job_relevance.rescore_job")
def rescore_job_task(account_id: int, job_id: int) -> dict[str, int | bool]:
    session_factory = get_session_factory()
    with session_factory() as session:
        job = rescore_job(session, account_id=account_id, job_id=job_id)
        session.commit()
        return {"job_id": job_id, "rescored": bool(job)}


@celery_app.task(name="app.tasks.job_relevance.rescore_account_jobs")
def rescore_account_jobs_task(account_id: int) -> dict[str, int]:
    session_factory = get_session_factory()
    with session_factory() as session:
        rescored = rescore_account_jobs_now(session, account_id=account_id)
        return {"account_id": account_id, "rescored": rescored}


@celery_app.task(name="app.tasks.job_relevance.evaluate_job_batch")
def evaluate_job_batch_task(account_id: int, job_ids: list[int]) -> dict[str, int]:
    session_factory = get_session_factory()
    with session_factory() as session:
        processed = evaluate_job_batch_now(
            session, account_id=account_id, job_ids=job_ids)
        return {"account_id": account_id, "processed": processed}
