from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlparse

from app.domains.applications.platform_matrix import (
    driver_family_for,
    platform_definition_for,
    platform_label,
)
from app.domains.sources.url_normalization import (
    derive_greenhouse_board_token_from_url,
    derive_greenhouse_job_post_id_from_url,
    derive_lever_company_slug_from_url,
    derive_lever_posting_id_from_url,
)


_GH_EMBED_PATTERN = re.compile(
    r'(?:boards|job-boards)\.greenhouse\.io/embed/job_board(?:/js)?\?for=([^&"\'>\s]+)',
    re.IGNORECASE,
)
_LEVER_EMBED_PATTERN = re.compile(
    r'api\.(?:eu\.)?lever\.co/v0/postings/([^/?&"\'>\s]+)',
    re.IGNORECASE,
)
_ASHBY_EMBED_PATTERN = re.compile(
    r'jobs\.ashbyhq\.com/([^/?&"\'>\s]+)',
    re.IGNORECASE,
)
_LEVER_POSTING_ID_PATTERN = re.compile(r"^[0-9a-f-]{8,}$", re.IGNORECASE)


COMPATIBILITY_LABELS = {
    "api_compatible": "API-compatible",
    "browser_compatible": "Browser-compatible",
    "manual_only": "Manual only",
    "resolution_failed": "Resolution failed",
}

COMPATIBILITY_PRIORITIES = {
    "resolution_failed": 25,
    "manual_only": 100,
    "browser_compatible": 200,
    "api_compatible": 300,
}


@dataclass(frozen=True, slots=True)
class ClassifiedTarget:
    target_type: str
    destination_url: str
    compatibility_state: str
    compatibility_reason: str | None
    metadata: dict[str, Any] = field(default_factory=dict)


def compatibility_label(value: str | None) -> str:
    if not value:
        return "Unknown"
    return COMPATIBILITY_LABELS.get(value, value.replace("_", " ").title())


def compatibility_priority_for(value: str | None) -> int:
    if not value:
        return 0
    return COMPATIBILITY_PRIORITIES.get(value, 0)


def compatibility_state_for(
    *,
    destination_url: str | None,
    target_type: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    metadata = metadata or {}
    configured = metadata.get("compatibility_state")
    if isinstance(configured, str) and configured.strip():
        return configured.strip().lower()

    definition = platform_definition_for(
        destination_url=destination_url,
        target_type=target_type,
        metadata=metadata,
    )
    driver_family = driver_family_for(
        destination_url=destination_url,
        target_type=target_type,
        metadata=metadata,
    )
    if definition.family == "external":
        return "manual_only"
    if driver_family == "direct_api":
        return "api_compatible"
    if driver_family == "browser":
        return "browser_compatible"
    return "manual_only"


def classify_resolved_target(
    *,
    source_url: str,
    resolved_url: str,
    link_kind: str,
    link_label: str | None = None,
    failure_reason: str | None = None,
    page_body: str | None = None,
) -> ClassifiedTarget:
    metadata: dict[str, Any] = {
        "source_url": source_url,
        "resolved_destination_url": resolved_url,
        "link_kind": link_kind,
        "link_label": link_label,
        "platform_label": None,
    }

    if failure_reason:
        metadata["compatibility_state"] = "resolution_failed"
        metadata["compatibility_reason"] = failure_reason
        metadata["resolution_failed"] = True
        return ClassifiedTarget(
            target_type="external_link",
            destination_url=source_url,
            compatibility_state="resolution_failed",
            compatibility_reason=failure_reason,
            metadata=metadata,
        )

    if page_body:
        sniffed = _sniff_ats_from_page_body(page_body, resolved_url, metadata)
        if sniffed is not None:
            return sniffed

    definition = platform_definition_for(destination_url=resolved_url)

    greenhouse_board_token, greenhouse_job_post_id = _derive_greenhouse_from_any_host(resolved_url)
    if greenhouse_board_token and greenhouse_job_post_id:
        metadata.update(
            {
                "platform_family": "greenhouse",
                "platform_label": platform_label("greenhouse"),
                "driver_family": "direct_api",
                "compatibility_state": "api_compatible",
                "board_token": greenhouse_board_token,
                "job_post_id": greenhouse_job_post_id,
            }
        )
        return ClassifiedTarget(
            target_type="greenhouse_apply",
            destination_url=resolved_url,
            compatibility_state="api_compatible",
            compatibility_reason=None,
            metadata=metadata,
        )

    lever_company_slug = derive_lever_company_slug_from_url(resolved_url)
    lever_posting_id = derive_lever_posting_id_from_url(resolved_url)
    if definition.family == "lever" and lever_company_slug and lever_posting_id:
        metadata.update(
            {
                "platform_family": "lever",
                "platform_label": platform_label("lever"),
                "driver_family": "direct_api",
                "compatibility_state": "api_compatible",
                "company_slug": lever_company_slug,
                "posting_id": lever_posting_id,
            }
        )
        return ClassifiedTarget(
            target_type="lever_apply",
            destination_url=resolved_url,
            compatibility_state="api_compatible",
            compatibility_reason=None,
            metadata=metadata,
        )

    driver_family = driver_family_for(destination_url=resolved_url)
    compatibility_state = compatibility_state_for(destination_url=resolved_url, metadata={})

    metadata.update(
        {
            "platform_family": definition.family,
            "platform_label": definition.label,
            "driver_family": driver_family,
            "compatibility_state": compatibility_state,
        }
    )

    if definition.family == "linkedin":
        metadata["linkedin_job_id"] = _extract_linkedin_job_id(resolved_url)
        return ClassifiedTarget(
            target_type="linkedin_easy_apply",
            destination_url=resolved_url,
            compatibility_state=compatibility_state,
            compatibility_reason=None,
            metadata=metadata,
        )

    if definition.family == "workday":
        return ClassifiedTarget(
            target_type="workday_apply",
            destination_url=resolved_url,
            compatibility_state=compatibility_state,
            compatibility_reason=None,
            metadata=metadata,
        )

    if definition.family == "icims":
        return ClassifiedTarget(
            target_type="icims_apply",
            destination_url=resolved_url,
            compatibility_state=compatibility_state,
            compatibility_reason=None,
            metadata=metadata,
        )

    if definition.family == "jobvite":
        return ClassifiedTarget(
            target_type="jobvite_apply",
            destination_url=resolved_url,
            compatibility_state=compatibility_state,
            compatibility_reason=None,
            metadata=metadata,
        )

    if definition.family == "ashby":
        job_posting_id = _extract_ashby_job_posting_id(resolved_url)
        if job_posting_id:
            metadata["job_posting_id"] = job_posting_id
        return ClassifiedTarget(
            target_type="ashby_apply",
            destination_url=resolved_url,
            compatibility_state=compatibility_state,
            compatibility_reason=None,
            metadata=metadata,
        )

    if definition.family == "smartrecruiters":
        return ClassifiedTarget(
            target_type="smartrecruiters_apply",
            destination_url=resolved_url,
            compatibility_state=compatibility_state,
            compatibility_reason=None,
            metadata=metadata,
        )

    if definition.family != "external":
        metadata["compatibility_reason"] = (
            f"{definition.label} links are recognized and routed as {compatibility_label(compatibility_state).lower()}."
        )
        return ClassifiedTarget(
            target_type="external_link",
            destination_url=resolved_url,
            compatibility_state=compatibility_state,
            compatibility_reason=metadata["compatibility_reason"],
            metadata=metadata,
        )

    metadata.update(
        {
            "platform_family": "generic_career_page",
            "platform_label": platform_label("generic_career_page"),
            "driver_family": "browser",
            "compatibility_state": "browser_compatible",
            "compatibility_reason": "Unknown platform — will attempt via generic browser automation.",
        }
    )
    return ClassifiedTarget(
        target_type="generic_career_page",
        destination_url=resolved_url,
        compatibility_state="browser_compatible",
        compatibility_reason=metadata["compatibility_reason"],
        metadata=metadata,
    )


_GREENHOUSE_HOSTS = ("greenhouse.io", "boards.greenhouse.io", "boards-api.greenhouse.io")


def _sniff_ats_from_page_body(
    page_body: str,
    resolved_url: str,
    metadata: dict[str, Any],
) -> ClassifiedTarget | None:
    gh_match = _GH_EMBED_PATTERN.search(page_body)
    if gh_match:
        board_token = gh_match.group(1)
        parsed_url = urlparse(resolved_url)
        gh_jid_values = parse_qs(parsed_url.query).get("gh_jid")
        job_post_id = gh_jid_values[0] if gh_jid_values else None

        path_segments = [s for s in parsed_url.path.split("/") if s.isdigit()]
        if not job_post_id and path_segments:
            job_post_id = path_segments[-1]

        if board_token and job_post_id:
            metadata.update(
                {
                    "platform_family": "greenhouse",
                    "platform_label": platform_label("greenhouse"),
                    "driver_family": "direct_api",
                    "compatibility_state": "api_compatible",
                    "board_token": board_token,
                    "job_post_id": job_post_id,
                }
            )
            return ClassifiedTarget(
                target_type="greenhouse_apply",
                destination_url=resolved_url,
                compatibility_state="api_compatible",
                compatibility_reason=None,
                metadata=metadata,
            )

        metadata.update(
            {
                "platform_family": "greenhouse",
                "platform_label": platform_label("greenhouse"),
                "driver_family": "browser",
                "compatibility_state": "browser_compatible",
                "board_token": board_token,
                "compatibility_reason": "Greenhouse-embedded career page — job post ID not found in URL.",
            }
        )
        return ClassifiedTarget(
            target_type="generic_career_page",
            destination_url=resolved_url,
            compatibility_state="browser_compatible",
            compatibility_reason=metadata["compatibility_reason"],
            metadata=metadata,
        )

    lever_match = _LEVER_EMBED_PATTERN.search(page_body)
    if lever_match:
        company_slug = lever_match.group(1)
        parsed_url = urlparse(resolved_url)
        path_segments = [s for s in parsed_url.path.split("/") if s]
        posting_id = None
        for segment in reversed(path_segments):
            if _LEVER_POSTING_ID_PATTERN.match(segment):
                posting_id = segment
                break

        if company_slug and posting_id:
            metadata.update(
                {
                    "platform_family": "lever",
                    "platform_label": platform_label("lever"),
                    "driver_family": "direct_api",
                    "compatibility_state": "api_compatible",
                    "company_slug": company_slug,
                    "posting_id": posting_id,
                }
            )
            return ClassifiedTarget(
                target_type="lever_apply",
                destination_url=resolved_url,
                compatibility_state="api_compatible",
                compatibility_reason=None,
                metadata=metadata,
            )

    ashby_match = _ASHBY_EMBED_PATTERN.search(page_body)
    if ashby_match:
        org_name = ashby_match.group(1)
        metadata.update(
            {
                "platform_family": "ashby",
                "platform_label": platform_label("ashby"),
                "driver_family": "browser",
                "compatibility_state": "browser_compatible",
                "org_name": org_name,
                "compatibility_reason": "Ashby-embedded career page — routed via browser driver.",
            }
        )
        return ClassifiedTarget(
            target_type="generic_career_page",
            destination_url=resolved_url,
            compatibility_state="browser_compatible",
            compatibility_reason=metadata["compatibility_reason"],
            metadata=metadata,
        )

    return None


def _derive_greenhouse_from_any_host(url: str | None) -> tuple[str | None, str | None]:
    if not url:
        return None, None
    parsed = urlparse(url)
    host = parsed.netloc.lower()

    if not any(host == h or host.endswith(f".{h}") for h in _GREENHOUSE_HOSTS):
        return None, None

    return derive_greenhouse_board_token_from_url(url), derive_greenhouse_job_post_id_from_url(url)


def _extract_ashby_job_posting_id(url: str) -> str | None:
    parsed = urlparse(url)
    segments = [s for s in parsed.path.split("/") if s]
    for segment in segments:
        if _LEVER_POSTING_ID_PATTERN.match(segment):
            return segment
    return None


def _extract_linkedin_job_id(url: str) -> str | None:
    segments = [segment for segment in url.split("/") if segment]
    for index, segment in enumerate(segments):
        if segment == "view" and index + 1 < len(segments):
            return segments[index + 1].split("?")[0]
    return None
