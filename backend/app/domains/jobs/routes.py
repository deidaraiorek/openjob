from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.domains.accounts.dependencies import get_current_account
from app.domains.accounts.models import Account
from app.domains.jobs.models import ApplyTarget, Job, JobRelevanceEvaluation, JobRelevanceTask, JobSighting
from app.domains.jobs.relevance import apply_relevance_result
from app.domains.questions.models import QuestionTask
from app.domains.applications.models import ApplicationEvent, ApplicationRun
from app.integrations.openai.job_relevance import JobRelevanceResult
from app.tasks.job_relevance import rescore_job
from app.db.session import get_db_session

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobSightingResponse(BaseModel):
    id: int
    source_id: int | None
    external_job_id: str | None
    listing_url: str
    apply_url: str | None


class ApplyTargetResponse(BaseModel):
    id: int
    target_type: str
    destination_url: str
    is_preferred: bool


class QuestionTaskSummary(BaseModel):
    id: int
    prompt_text: str
    status: str
    linked_answer_entry_id: int | None


class ApplicationEventResponse(BaseModel):
    id: int
    event_type: str
    payload: dict


class ApplicationRunResponse(BaseModel):
    id: int
    status: str
    apply_target_id: int | None
    events: list[ApplicationEventResponse]


class JobRelevanceEvaluationResponse(BaseModel):
    id: int
    decision: str
    source: str
    score: float | None
    summary: str | None
    matched_signals: list[str]
    concerns: list[str]
    model_name: str | None
    failure_cause: str | None
    decision_phase: str | None
    decision_rationale_type: str | None
    decision_policy_snapshot: dict | None = None
    derived_profile_hints: dict | None = None


class JobRelevanceUpdateRequest(BaseModel):
    decision: str
    summary: str | None = None


class JobRelevanceUpdateResponse(BaseModel):
    job_id: int
    relevance_decision: str
    relevance_source: str
    relevance_score: float | None
    relevance_summary: str | None
    relevance_failure_cause: str | None
    relevance_decision_phase: str | None
    relevance_decision_rationale_type: str | None
    pending_relevance_phase: str | None = None
    pending_relevance_attempt_count: int | None = None
    pending_relevance_failure_cause: str | None = None
    pending_relevance_next_retry_at: str | None = None


class JobRescoreResponse(BaseModel):
    job_id: int
    relevance_decision: str
    relevance_source: str
    relevance_score: float | None
    relevance_summary: str | None
    relevance_failure_cause: str | None
    relevance_decision_phase: str | None
    relevance_decision_rationale_type: str | None
    pending_relevance_phase: str | None = None
    pending_relevance_attempt_count: int | None = None
    pending_relevance_failure_cause: str | None = None
    pending_relevance_next_retry_at: str | None = None


class JobDetailResponse(BaseModel):
    id: int
    canonical_key: str
    company_name: str
    title: str
    location: str | None
    status: str
    relevance_decision: str
    relevance_source: str
    relevance_score: float | None
    relevance_summary: str | None
    relevance_failure_cause: str | None
    relevance_decision_phase: str | None
    relevance_decision_rationale_type: str | None
    pending_relevance_phase: str | None = None
    pending_relevance_attempt_count: int | None = None
    pending_relevance_failure_cause: str | None = None
    pending_relevance_next_retry_at: str | None = None
    sightings: list[JobSightingResponse]
    preferred_apply_target: ApplyTargetResponse | None
    question_tasks: list[QuestionTaskSummary]
    application_runs: list[ApplicationRunResponse]
    relevance_evaluations: list[JobRelevanceEvaluationResponse]


class JobListItemResponse(BaseModel):
    id: int
    canonical_key: str
    company_name: str
    title: str
    location: str | None
    status: str
    relevance_decision: str
    relevance_source: str
    relevance_score: float | None
    relevance_summary: str | None
    relevance_failure_cause: str | None
    relevance_decision_phase: str | None
    relevance_decision_rationale_type: str | None
    pending_relevance_phase: str | None = None
    pending_relevance_attempt_count: int | None = None
    pending_relevance_failure_cause: str | None = None
    pending_relevance_next_retry_at: str | None = None
    preferred_apply_target_type: str | None
    sighting_count: int
    open_question_task_count: int
    latest_application_run_status: str | None


def serialize_sighting(sighting: JobSighting) -> JobSightingResponse:
    return JobSightingResponse(
        id=sighting.id,
        source_id=sighting.source_id,
        external_job_id=sighting.external_job_id,
        listing_url=sighting.listing_url,
        apply_url=sighting.apply_url,
    )


def serialize_apply_target(target: ApplyTarget) -> ApplyTargetResponse:
    return ApplyTargetResponse(
        id=target.id,
        target_type=target.target_type,
        destination_url=target.destination_url,
        is_preferred=target.is_preferred,
    )


def serialize_question_summary(task: QuestionTask) -> QuestionTaskSummary:
    return QuestionTaskSummary(
        id=task.id,
        prompt_text=task.prompt_text,
        status=task.status,
        linked_answer_entry_id=task.linked_answer_entry_id,
    )


def serialize_event(event: ApplicationEvent) -> ApplicationEventResponse:
    return ApplicationEventResponse(
        id=event.id,
        event_type=event.event_type,
        payload=event.payload,
    )


def serialize_relevance_evaluation(
    evaluation: JobRelevanceEvaluation,
) -> JobRelevanceEvaluationResponse:
    return JobRelevanceEvaluationResponse(
        id=evaluation.id,
        decision=evaluation.decision,
        source=evaluation.source,
        score=evaluation.score,
        summary=evaluation.summary,
        matched_signals=evaluation.matched_signals,
        concerns=evaluation.concerns,
        model_name=evaluation.model_name,
        failure_cause=evaluation.payload.get("failure_cause"),
        decision_phase=evaluation.payload.get("decision_phase"),
        decision_rationale_type=evaluation.payload.get("decision_rationale_type"),
        decision_policy_snapshot=evaluation.payload.get("decision_policy_snapshot"),
        derived_profile_hints=evaluation.payload.get("derived_profile_hints"),
    )


def serialize_run(run: ApplicationRun) -> ApplicationRunResponse:
    ordered_events = sorted(run.events, key=lambda event: event.id)
    return ApplicationRunResponse(
        id=run.id,
        status=run.status,
        apply_target_id=run.apply_target_id,
        events=[serialize_event(event) for event in ordered_events],
    )


def effective_relevance_decision(job: Job) -> str:
    if job.relevance_decision:
        return job.relevance_decision
    if job.relevance_evaluations:
        return job.relevance_evaluations[0].decision
    if job.status == "filtered_out":
        return "reject"
    return "match"


def effective_pending_relevance_task(job: Job) -> JobRelevanceTask | None:
    if not job.relevance_tasks:
        return None
    return sorted(job.relevance_tasks, key=lambda item: (item.available_at, item.id))[0]


def effective_relevance_source(job: Job) -> str | None:
    if job.relevance_source:
        return job.relevance_source
    if job.relevance_evaluations:
        return job.relevance_evaluations[0].source
    return None


def effective_relevance_score(job: Job) -> float | None:
    if job.relevance_score is not None:
        return job.relevance_score
    if job.relevance_evaluations:
        return job.relevance_evaluations[0].score
    return None


def effective_relevance_summary(job: Job) -> str | None:
    if job.relevance_summary:
        return job.relevance_summary
    if job.relevance_evaluations:
        return job.relevance_evaluations[0].summary
    return None


def effective_relevance_failure_cause(job: Job) -> str | None:
    pending_task = effective_pending_relevance_task(job)
    if effective_relevance_decision(job) == "pending" and pending_task is not None:
        return pending_task.last_failure_cause
    if job.relevance_evaluations:
        return job.relevance_evaluations[0].payload.get("failure_cause")
    return None


def effective_relevance_decision_phase(job: Job) -> str | None:
    pending_task = effective_pending_relevance_task(job)
    if effective_relevance_decision(job) == "pending" and pending_task is not None:
        return pending_task.phase
    if job.relevance_evaluations:
        return job.relevance_evaluations[0].payload.get("decision_phase")
    return None


def effective_relevance_decision_rationale_type(job: Job) -> str | None:
    if job.relevance_evaluations:
        return job.relevance_evaluations[0].payload.get("decision_rationale_type")
    return None


@router.get("", response_model=list[JobListItemResponse])
def list_jobs(
    relevance: str = Query(default="active"),
    current_account: Account = Depends(get_current_account),
    session: Session = Depends(get_db_session),
) -> list[JobListItemResponse]:
    jobs = session.scalars(
        select(Job)
        .where(Job.account_id == current_account.id)
        .options(
            selectinload(Job.sightings),
            selectinload(Job.apply_targets),
            selectinload(Job.question_tasks),
            selectinload(Job.application_runs),
            selectinload(Job.relevance_evaluations),
            selectinload(Job.relevance_tasks),
        )
        .order_by(Job.id.desc()),
    ).all()

    items: list[JobListItemResponse] = []
    for job in jobs:
        effective_decision = effective_relevance_decision(job)
        if relevance == "active" and effective_decision == "reject":
            continue
        if relevance == "active" and effective_decision == "pending":
            continue
        if relevance in {"match", "review", "reject", "pending"} and effective_decision != relevance:
            continue
        pending_task = effective_pending_relevance_task(job)
        preferred_target = next(
            (target for target in job.apply_targets if target.is_preferred),
            None,
        )
        latest_run = max(job.application_runs, key=lambda item: item.id, default=None)
        items.append(
            JobListItemResponse(
                id=job.id,
                canonical_key=job.canonical_key,
                company_name=job.company_name,
                title=job.title,
                location=job.location,
                status=job.status,
                relevance_decision=effective_decision,
                relevance_source=effective_relevance_source(job),
                relevance_score=effective_relevance_score(job),
                relevance_summary=effective_relevance_summary(job),
                relevance_failure_cause=effective_relevance_failure_cause(job),
                relevance_decision_phase=effective_relevance_decision_phase(job),
                relevance_decision_rationale_type=effective_relevance_decision_rationale_type(job),
                pending_relevance_phase=pending_task.phase if pending_task else None,
                pending_relevance_attempt_count=pending_task.attempt_count if pending_task else None,
                pending_relevance_failure_cause=pending_task.last_failure_cause if pending_task else None,
                pending_relevance_next_retry_at=pending_task.available_at.isoformat() if pending_task else None,
                preferred_apply_target_type=preferred_target.target_type if preferred_target else None,
                sighting_count=len(job.sightings),
                open_question_task_count=len(
                    [task for task in job.question_tasks if task.status in {"new", "pending"}]
                ),
                latest_application_run_status=latest_run.status if latest_run else None,
            )
        )

    return items


@router.patch("/{job_id}/relevance", response_model=JobRelevanceUpdateResponse)
def update_job_relevance(
    job_id: int,
    payload: JobRelevanceUpdateRequest,
    current_account: Account = Depends(get_current_account),
    session: Session = Depends(get_db_session),
) -> JobRelevanceUpdateResponse:
    job = session.scalar(
        select(Job).where(Job.id == job_id, Job.account_id == current_account.id),
    )
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    if payload.decision not in {"match", "reject", "review"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid relevance decision")

    source = {
        "match": "manual_include",
        "reject": "manual_exclude",
        "review": "manual_review",
    }[payload.decision]
    summary = payload.summary or {
        "match": "User manually marked this job as relevant.",
        "reject": "User manually marked this job as out of scope.",
        "review": "User manually marked this job for review.",
    }[payload.decision]

    apply_relevance_result(
        session,
        account_id=current_account.id,
        job=job,
        result=JobRelevanceResult(
            decision=payload.decision,
            score=None,
            summary=summary,
            matched_signals=[],
            concerns=["manual override"],
            source=source,
            model_name=None,
            failure_cause=None,
            payload={"manual": True},
        ),
        profile=None,
    )
    for task in list(job.relevance_tasks):
        session.delete(task)
    session.commit()
    session.refresh(job)
    pending_task = effective_pending_relevance_task(job)
    return JobRelevanceUpdateResponse(
        job_id=job.id,
        relevance_decision=effective_relevance_decision(job),
        relevance_source=effective_relevance_source(job) or source,
        relevance_score=effective_relevance_score(job),
        relevance_summary=effective_relevance_summary(job),
        relevance_failure_cause=effective_relevance_failure_cause(job),
        relevance_decision_phase=effective_relevance_decision_phase(job),
        relevance_decision_rationale_type=effective_relevance_decision_rationale_type(job),
        pending_relevance_phase=pending_task.phase if pending_task else None,
        pending_relevance_attempt_count=pending_task.attempt_count if pending_task else None,
        pending_relevance_failure_cause=pending_task.last_failure_cause if pending_task else None,
        pending_relevance_next_retry_at=pending_task.available_at.isoformat() if pending_task else None,
    )


@router.post("/{job_id}/relevance/rescore", response_model=JobRescoreResponse)
def rescore_job_route(
    job_id: int,
    current_account: Account = Depends(get_current_account),
    session: Session = Depends(get_db_session),
) -> JobRescoreResponse:
    job = rescore_job(session, account_id=current_account.id, job_id=job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    session.commit()
    session.refresh(job)
    pending_task = effective_pending_relevance_task(job)
    return JobRescoreResponse(
        job_id=job.id,
        relevance_decision=effective_relevance_decision(job),
        relevance_source=effective_relevance_source(job) or job.relevance_source,
        relevance_score=effective_relevance_score(job),
        relevance_summary=effective_relevance_summary(job),
        relevance_failure_cause=effective_relevance_failure_cause(job),
        relevance_decision_phase=effective_relevance_decision_phase(job),
        relevance_decision_rationale_type=effective_relevance_decision_rationale_type(job),
        pending_relevance_phase=pending_task.phase if pending_task else None,
        pending_relevance_attempt_count=pending_task.attempt_count if pending_task else None,
        pending_relevance_failure_cause=pending_task.last_failure_cause if pending_task else None,
        pending_relevance_next_retry_at=pending_task.available_at.isoformat() if pending_task else None,
    )


@router.get("/{job_id}", response_model=JobDetailResponse)
def get_job_detail(
    job_id: int,
    current_account: Account = Depends(get_current_account),
    session: Session = Depends(get_db_session),
) -> JobDetailResponse:
    job = session.scalar(
        select(Job)
        .where(Job.id == job_id, Job.account_id == current_account.id)
        .options(
            selectinload(Job.sightings),
            selectinload(Job.apply_targets),
            selectinload(Job.question_tasks),
            selectinload(Job.application_runs).selectinload(ApplicationRun.events),
            selectinload(Job.relevance_evaluations),
            selectinload(Job.relevance_tasks),
        ),
    )
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    preferred_target = next(
        (target for target in job.apply_targets if target.is_preferred),
        None,
    )
    pending_task = effective_pending_relevance_task(job)

    return JobDetailResponse(
        id=job.id,
        canonical_key=job.canonical_key,
        company_name=job.company_name,
        title=job.title,
        location=job.location,
        status=job.status,
        relevance_decision=effective_relevance_decision(job),
        relevance_source=effective_relevance_source(job),
        relevance_score=effective_relevance_score(job),
        relevance_summary=effective_relevance_summary(job),
        relevance_failure_cause=effective_relevance_failure_cause(job),
        relevance_decision_phase=effective_relevance_decision_phase(job),
        relevance_decision_rationale_type=effective_relevance_decision_rationale_type(job),
        pending_relevance_phase=pending_task.phase if pending_task else None,
        pending_relevance_attempt_count=pending_task.attempt_count if pending_task else None,
        pending_relevance_failure_cause=pending_task.last_failure_cause if pending_task else None,
        pending_relevance_next_retry_at=pending_task.available_at.isoformat() if pending_task else None,
        sightings=[serialize_sighting(sighting) for sighting in sorted(job.sightings, key=lambda item: item.id)],
        preferred_apply_target=serialize_apply_target(preferred_target) if preferred_target else None,
        question_tasks=[
            serialize_question_summary(task)
            for task in sorted(job.question_tasks, key=lambda item: item.id)
        ],
        application_runs=[
            serialize_run(run)
            for run in sorted(job.application_runs, key=lambda item: item.id)
        ],
        relevance_evaluations=[
            serialize_relevance_evaluation(evaluation)
            for evaluation in job.relevance_evaluations
        ],
    )
