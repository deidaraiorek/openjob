from __future__ import annotations

from app.domains.jobs.models import ApplyTarget, Job

TARGET_PRIORITY = {
    "greenhouse_apply": 100,
    "lever_apply": 90,
    "linkedin_easy_apply": 50,
    "external_link": 10,
}


def get_target_priority(target_type: str) -> int:
    return TARGET_PRIORITY.get(target_type, 0)


def refresh_preferred_apply_target(job: Job) -> ApplyTarget | None:
    if not job.apply_targets:
        return None

    preferred = max(
        job.apply_targets,
        key=lambda target: (get_target_priority(target.target_type), -target.id if target.id else 0),
    )
    for target in job.apply_targets:
        target.is_preferred = target is preferred
    return preferred
