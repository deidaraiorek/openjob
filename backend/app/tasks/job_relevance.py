from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.celery_app import celery_app
from app.domains.jobs.models import Job, JobSighting
from app.domains.jobs.relevance import apply_relevance_result, evaluate_job_relevance
from app.domains.role_profiles.models import RoleProfile
from app.db.session import get_session_factory


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
