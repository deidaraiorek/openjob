from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.celery_app import celery_app
from app.config import get_settings
from app.domains.jobs.models import Job, JobSighting
from app.domains.jobs.relevance import (
    apply_relevance_result,
    build_batch_request_for_job,
    evaluate_job_relevance,
)
from app.domains.role_profiles.models import RoleProfile
from app.db.session import get_session_factory
from app.integrations.openai.job_relevance import classify_job_relevance_batch


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
    batch_size = max(1, settings.sync_full_relevance_batch_size)
    processed = 0

    for index in range(0, len(jobs), batch_size):
        chunk = jobs[index: index + batch_size]
        requests = [build_batch_request_for_job(job) for job in chunk]
        results = classify_job_relevance_batch(
            profile, requests, settings=settings)
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
