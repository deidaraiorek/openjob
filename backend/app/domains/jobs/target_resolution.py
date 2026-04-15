from __future__ import annotations

from app.domains.jobs.models import ApplyTarget, Job
from app.domains.applications.platform_matrix import platform_definition_for, target_priority_for
from app.domains.sources.link_classification import compatibility_priority_for, compatibility_state_for


def get_target_priority(target: ApplyTarget) -> int:
    return get_target_priority_values(
        destination_url=target.destination_url,
        target_type=target.target_type,
        metadata=target.metadata_json,
    )


def get_target_priority_values(
    *,
    destination_url: str,
    target_type: str,
    metadata: dict | None,
) -> int:
    metadata = metadata or {}
    definition = platform_definition_for(
        destination_url=destination_url,
        target_type=target_type,
        metadata=metadata,
    )
    base_priority = target_priority_for(
        destination_url=destination_url,
        target_type=target_type,
        metadata=metadata,
    )
    compatibility_state = compatibility_state_for(
        destination_url=destination_url,
        target_type=target_type,
        metadata=metadata,
    )
    specificity_bonus = 50 if target_type != "external_link" else 0
    resolved_bonus = 25 if metadata.get("resolved_destination_url") else 0
    implemented_bonus = 500 if definition.implemented else 0
    non_external_bonus = 100 if definition.family != "external" else 0
    return (
        implemented_bonus
        + compatibility_priority_for(compatibility_state)
        + non_external_bonus
        + specificity_bonus
        + resolved_bonus
        + base_priority
    )


def refresh_preferred_apply_target(job: Job) -> ApplyTarget | None:
    if not job.apply_targets:
        return None

    preferred = max(
        job.apply_targets,
        key=lambda target: (get_target_priority(target), -target.id if target.id else 0),
    )
    for target in job.apply_targets:
        target.is_preferred = target is preferred
    return preferred
