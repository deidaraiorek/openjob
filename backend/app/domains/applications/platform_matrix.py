from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


PLATFORM_FAMILIES = {
    "external",
    "greenhouse",
    "lever",
    "linkedin",
    "ashby",
    "smartrecruiters",
    "workday",
    "icims",
    "jobvite",
    "generic_career_page",
}

DRIVER_FAMILIES = {"manual", "direct_api", "browser"}
CREDENTIAL_POLICIES = {"not_needed", "optional", "tenant_required", "unsupported_with_mfa"}


@dataclass(frozen=True, slots=True)
class PlatformDefinition:
    family: str
    label: str
    driver_family: str
    credential_policy: str
    rollout_tier: str
    priority: int
    implemented: bool
    host_patterns: tuple[str, ...] = ()


PLATFORM_REGISTRY: dict[str, PlatformDefinition] = {
    "external": PlatformDefinition(
        family="external",
        label="External Link",
        driver_family="manual",
        credential_policy="not_needed",
        rollout_tier="manual",
        priority=10,
        implemented=False,
    ),
    "greenhouse": PlatformDefinition(
        family="greenhouse",
        label="Greenhouse",
        driver_family="direct_api",
        credential_policy="not_needed",
        rollout_tier="baseline",
        priority=100,
        implemented=True,
        host_patterns=("greenhouse.io",),
    ),
    "lever": PlatformDefinition(
        family="lever",
        label="Lever",
        driver_family="direct_api",
        credential_policy="not_needed",
        rollout_tier="baseline",
        priority=90,
        implemented=True,
        host_patterns=("lever.co",),
    ),
    "linkedin": PlatformDefinition(
        family="linkedin",
        label="LinkedIn",
        driver_family="browser",
        credential_policy="optional",
        rollout_tier="baseline",
        priority=60,
        implemented=True,
        host_patterns=("linkedin.com",),
    ),
    "ashby": PlatformDefinition(
        family="ashby",
        label="Ashby",
        driver_family="direct_api",
        credential_policy="not_needed",
        rollout_tier="phase_1",
        priority=80,
        implemented=True,
        host_patterns=("ashbyhq.com",),
    ),
    "smartrecruiters": PlatformDefinition(
        family="smartrecruiters",
        label="SmartRecruiters",
        driver_family="direct_api",
        credential_policy="not_needed",
        rollout_tier="phase_1",
        priority=75,
        implemented=True,
        host_patterns=("smartrecruiters.com",),
    ),
    "workday": PlatformDefinition(
        family="workday",
        label="Workday",
        driver_family="browser",
        credential_policy="optional",
        rollout_tier="phase_2",
        priority=50,
        implemented=True,
        host_patterns=("myworkdayjobs.com", "myworkdaysite.com", "workday.com", "workdayjobs.com"),
    ),
    "icims": PlatformDefinition(
        family="icims",
        label="iCIMS",
        driver_family="browser",
        credential_policy="tenant_required",
        rollout_tier="phase_2",
        priority=45,
        implemented=True,
        host_patterns=("icims.com",),
    ),
    "jobvite": PlatformDefinition(
        family="jobvite",
        label="Jobvite",
        driver_family="browser",
        credential_policy="tenant_required",
        rollout_tier="phase_2",
        priority=40,
        implemented=True,
        host_patterns=("jobvite.com",),
    ),
    "generic_career_page": PlatformDefinition(
        family="generic_career_page",
        label="Generic Career Page",
        driver_family="browser",
        credential_policy="not_needed",
        rollout_tier="phase_3",
        priority=5,
        implemented=True,
    ),
}

TARGET_TYPE_PLATFORM_MAP = {
    "greenhouse_apply": "greenhouse",
    "lever_apply": "lever",
    "linkedin_easy_apply": "linkedin",
    "ashby_apply": "ashby",
    "smartrecruiters_apply": "smartrecruiters",
    "workday_apply": "workday",
    "icims_apply": "icims",
    "jobvite_apply": "jobvite",
    "generic_career_page": "generic_career_page",
    "external_link": "external",
}


def normalize_platform_family(value: str) -> str:
    normalized = value.strip().lower().replace(" ", "_")
    if normalized not in PLATFORM_FAMILIES:
        raise ValueError(f"Unsupported platform family: {value}")
    return normalized


def platform_label(value: str) -> str:
    definition = PLATFORM_REGISTRY.get(value)
    if definition is not None:
        return definition.label
    return value.replace("_", " ").title()


def normalize_tenant_host(value: str | None) -> str:
    if not value:
        return ""

    trimmed = value.strip()
    if not trimmed:
        return ""

    parsed = urlparse(trimmed if "://" in trimmed else f"https://{trimmed}")
    candidate = parsed.netloc or parsed.path
    return candidate.strip().lower().rstrip("/")


def host_for_destination_url(value: str | None) -> str:
    if not value:
        return ""
    parsed = urlparse(value)
    return parsed.netloc.lower().strip()


def detect_platform_family(*, destination_url: str | None, target_type: str | None = None, metadata: dict[str, Any] | None = None) -> str:
    metadata = metadata or {}

    configured_family = metadata.get("platform_family")
    if isinstance(configured_family, str) and configured_family.strip():
        return normalize_platform_family(configured_family)

    if target_type:
        mapped = TARGET_TYPE_PLATFORM_MAP.get(target_type)
        if mapped and mapped != "external":
            return mapped

    host = host_for_destination_url(destination_url)
    for family, definition in PLATFORM_REGISTRY.items():
        if family == "external":
            continue
        if any(host == pattern or host.endswith(f".{pattern}") for pattern in definition.host_patterns):
            return family

    return TARGET_TYPE_PLATFORM_MAP.get(target_type or "", "external")


def platform_definition_for(*, destination_url: str | None, target_type: str | None = None, metadata: dict[str, Any] | None = None) -> PlatformDefinition:
    family = detect_platform_family(destination_url=destination_url, target_type=target_type, metadata=metadata)
    return PLATFORM_REGISTRY[family]


def driver_family_for(*, destination_url: str | None, target_type: str | None = None, metadata: dict[str, Any] | None = None) -> str:
    metadata = metadata or {}
    configured = metadata.get("driver_family")
    if isinstance(configured, str) and configured.strip():
        normalized = configured.strip().lower()
        if normalized in DRIVER_FAMILIES:
            return normalized
    return platform_definition_for(destination_url=destination_url, target_type=target_type, metadata=metadata).driver_family


def credential_policy_for(*, destination_url: str | None, target_type: str | None = None, metadata: dict[str, Any] | None = None) -> str:
    metadata = metadata or {}
    configured = metadata.get("credential_policy")
    if isinstance(configured, str) and configured.strip():
        normalized = configured.strip().lower()
        if normalized in CREDENTIAL_POLICIES:
            return normalized
    return platform_definition_for(destination_url=destination_url, target_type=target_type, metadata=metadata).credential_policy


def target_priority_for(*, destination_url: str | None, target_type: str | None = None, metadata: dict[str, Any] | None = None) -> int:
    metadata = metadata or {}
    configured_priority = metadata.get("target_priority")
    if isinstance(configured_priority, int):
        return configured_priority
    return platform_definition_for(destination_url=destination_url, target_type=target_type, metadata=metadata).priority
