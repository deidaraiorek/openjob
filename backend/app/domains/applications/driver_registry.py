from __future__ import annotations

from dataclasses import dataclass

from app.domains.applications.platform_matrix import driver_family_for, platform_definition_for
from app.domains.jobs.models import ApplyTarget


@dataclass(frozen=True, slots=True)
class ApplicationDriver:
    key: str
    label: str
    driver_family: str


DIRECT_API_DRIVER = ApplicationDriver(
    key="direct_api",
    label="Direct API",
    driver_family="direct_api",
)
LINKEDIN_BROWSER_DRIVER = ApplicationDriver(
    key="linkedin_browser",
    label="LinkedIn browser automation",
    driver_family="browser",
)
AI_BROWSER_DRIVER = ApplicationDriver(
    key="ai_browser",
    label="AI browser agent",
    driver_family="browser",
)


def resolve_driver(target: ApplyTarget) -> ApplicationDriver:
    definition = platform_definition_for(
        destination_url=target.destination_url,
        target_type=target.target_type,
        metadata=target.metadata_json,
    )
    driver_family = driver_family_for(
        destination_url=target.destination_url,
        target_type=target.target_type,
        metadata=target.metadata_json,
    )
    if target.target_type in {"greenhouse_apply", "lever_apply", "ashby_apply", "smartrecruiters_apply"}:
        return DIRECT_API_DRIVER
    if definition.family == "linkedin":
        return LINKEDIN_BROWSER_DRIVER
    if driver_family == "direct_api":
        return DIRECT_API_DRIVER
    return AI_BROWSER_DRIVER
