from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.domains.applications.platform_matrix import platform_definition_for
from app.domains.jobs.deduplication import ApplyTargetCandidate, DiscoveryCandidate
from app.domains.jobs.target_resolution import get_target_priority_values
from app.domains.sources.link_classification import classify_resolved_target, compatibility_state_for


DEFAULT_LINK_RESOLUTION_TIMEOUT_SECONDS = 5.0
DEFAULT_LINK_RESOLUTION_MAX_REDIRECTS = 3
DEFAULT_LINK_RESOLUTION_MAX_LINKS_PER_CANDIDATE = 4


@dataclass(frozen=True, slots=True)
class ResolvedLink:
    source_url: str
    resolved_url: str
    redirect_chain: list[str]
    failure_reason: str | None = None
    page_body: str | None = None


def resolve_github_candidates(
    candidates: list[DiscoveryCandidate],
    *,
    settings: dict[str, Any] | None = None,
) -> list[DiscoveryCandidate]:
    resolution_settings = settings or {}
    cache: dict[str, ResolvedLink] = {}
    return [
        resolve_github_candidate(
            candidate,
            settings=resolution_settings,
            cache=cache,
        )
        for candidate in candidates
    ]


def resolve_github_candidate(
    candidate: DiscoveryCandidate,
    *,
    settings: dict[str, Any] | None = None,
    cache: dict[str, ResolvedLink] | None = None,
) -> DiscoveryCandidate:
    resolution_settings = settings or {}
    resolved_targets: list[ApplyTargetCandidate] = []
    resolution_records: list[dict[str, Any]] = []
    outbound_links = _extract_outbound_links(candidate)
    cache = cache if cache is not None else {}
    max_links = max(
        1,
        int(resolution_settings.get("link_resolution_max_links_per_candidate") or DEFAULT_LINK_RESOLUTION_MAX_LINKS_PER_CANDIDATE),
    )

    relevant_outbound_links = [link for link in outbound_links if link.get("kind") != "company"]
    for link in relevant_outbound_links[:max_links]:
        source_url = link["url"]
        if not source_url:
            continue

        resolved = cache.get(source_url)
        if resolved is None:
            resolved = resolve_link(
                source_url,
                timeout_seconds=float(
                    resolution_settings.get("link_resolution_timeout_seconds")
                    or DEFAULT_LINK_RESOLUTION_TIMEOUT_SECONDS
                ),
                max_redirects=int(
                    resolution_settings.get("link_resolution_max_redirects")
                    or DEFAULT_LINK_RESOLUTION_MAX_REDIRECTS
                ),
            )
            cache[source_url] = resolved

        classified = classify_resolved_target(
            source_url=source_url,
            resolved_url=resolved.resolved_url,
            link_kind=link.get("kind", "unknown"),
            link_label=link.get("label"),
            failure_reason=resolved.failure_reason,
            page_body=resolved.page_body,
        )
        _append_resolved_target(
            resolved_targets,
            ApplyTargetCandidate(
                destination_url=classified.destination_url,
                target_type=classified.target_type,
                metadata=classified.metadata,
            ),
        )
        resolution_records.append(
            {
                "source_url": source_url,
                "resolved_url": resolved.resolved_url,
                "redirect_chain": resolved.redirect_chain,
                "failure_reason": resolved.failure_reason,
                "target_type": classified.target_type,
                "compatibility_state": classified.compatibility_state,
                "compatibility_reason": classified.compatibility_reason,
                "link_kind": link.get("kind"),
                "link_label": link.get("label"),
            }
        )

    if not resolved_targets:
        fallback_url = candidate.apply_url or candidate.listing_url
        if fallback_url:
            fallback = classify_resolved_target(
                source_url=fallback_url,
                resolved_url=fallback_url,
                link_kind="fallback",
                failure_reason="No outbound links were available to classify.",
            )
            _append_resolved_target(
                resolved_targets,
                ApplyTargetCandidate(
                    destination_url=fallback.destination_url,
                    target_type=fallback.target_type,
                    metadata=fallback.metadata,
                ),
            )
            resolution_records.append(
                {
                    "source_url": fallback_url,
                    "resolved_url": fallback_url,
                    "redirect_chain": [],
                    "failure_reason": "No outbound links were available to classify.",
                    "target_type": fallback.target_type,
                    "compatibility_state": fallback.compatibility_state,
                    "compatibility_reason": fallback.compatibility_reason,
                    "link_kind": "fallback",
                    "link_label": None,
                }
            )

    preferred_target = _select_preferred_target(resolved_targets)
    candidate.apply_targets = resolved_targets
    candidate.raw_payload = {
        **candidate.raw_payload,
        "outbound_links": outbound_links,
        "link_resolution": resolution_records,
    }
    if preferred_target is not None:
        candidate.apply_url = preferred_target.destination_url
        candidate.apply_target_type = preferred_target.target_type
        candidate.metadata = {
            **candidate.metadata,
            **preferred_target.metadata,
        }
    return candidate


def summarize_candidate_targets(candidates: list[DiscoveryCandidate]) -> dict[str, int]:
    summary = {
        "api_compatible_targets": 0,
        "browser_compatible_targets": 0,
        "manual_only_targets": 0,
        "resolution_failed_targets": 0,
    }
    for candidate in candidates:
        target_candidates = list(candidate.apply_targets)
        if not target_candidates and candidate.apply_url and candidate.apply_target_type:
            target_candidates.append(
                ApplyTargetCandidate(
                    destination_url=candidate.apply_url,
                    target_type=candidate.apply_target_type,
                    metadata=candidate.metadata,
                )
            )
        for target in target_candidates:
            state = compatibility_state_for(
                destination_url=target.destination_url,
                target_type=target.target_type,
                metadata=target.metadata,
            )
            if state == "api_compatible":
                summary["api_compatible_targets"] += 1
            elif state == "browser_compatible":
                summary["browser_compatible_targets"] += 1
            elif state == "resolution_failed":
                summary["resolution_failed_targets"] += 1
            else:
                summary["manual_only_targets"] += 1
    return summary


def resolve_link(
    source_url: str,
    *,
    timeout_seconds: float = DEFAULT_LINK_RESOLUTION_TIMEOUT_SECONDS,
    max_redirects: int = DEFAULT_LINK_RESOLUTION_MAX_REDIRECTS,
) -> ResolvedLink:
    if not _should_probe_link(source_url):
        return ResolvedLink(source_url=source_url, resolved_url=source_url, redirect_chain=[])

    try:
        with httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=True,
            max_redirects=max_redirects,
            headers={"User-Agent": "OpenJob/0.1"},
        ) as client:
            response = client.get(source_url)
            response.raise_for_status()
            redirect_chain = [str(item.url) for item in response.history]
            content_type = response.headers.get("content-type", "")
            page_body = response.text if "html" in content_type else None
            return ResolvedLink(
                source_url=source_url,
                resolved_url=str(response.url),
                redirect_chain=redirect_chain,
                page_body=page_body,
            )
    except httpx.TimeoutException:
        return ResolvedLink(
            source_url=source_url,
            resolved_url=source_url,
            redirect_chain=[],
            failure_reason="Timed out while resolving the outbound link.",
        )
    except httpx.TooManyRedirects:
        return ResolvedLink(
            source_url=source_url,
            resolved_url=source_url,
            redirect_chain=[],
            failure_reason="The outbound link exceeded the redirect limit.",
        )
    except httpx.HTTPError as error:
        return ResolvedLink(
            source_url=source_url,
            resolved_url=source_url,
            redirect_chain=[],
            failure_reason=f"Unable to resolve the outbound link: {error}",
        )


def _extract_outbound_links(candidate: DiscoveryCandidate) -> list[dict[str, str | None]]:
    raw_outbound_links = candidate.raw_payload.get("outbound_links")
    if isinstance(raw_outbound_links, list):
        normalized_links = _normalize_outbound_links(raw_outbound_links)
        if normalized_links:
            return normalized_links

    return _normalize_outbound_links(
        [
            {"kind": "listing", "label": None, "url": candidate.listing_url},
            {"kind": "apply", "label": None, "url": candidate.apply_url},
        ]
    )


def _normalize_outbound_links(items: list[dict[str, Any]]) -> list[dict[str, str | None]]:
    links: list[dict[str, str | None]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not isinstance(url, str) or not url.strip():
            continue
        normalized_url = url.strip()
        if normalized_url in seen:
            continue
        seen.add(normalized_url)
        links.append(
            {
                "kind": str(item.get("kind") or "unknown"),
                "label": str(item["label"]) if isinstance(item.get("label"), str) else None,
                "url": normalized_url,
            }
        )
    return links


def _select_preferred_target(targets: list[ApplyTargetCandidate]) -> ApplyTargetCandidate | None:
    if not targets:
        return None
    return max(
        targets,
        key=lambda target: (
            get_target_priority_values(
                destination_url=target.destination_url,
                target_type=target.target_type,
                metadata=target.metadata,
            ),
            -len(target.destination_url),
        ),
    )


def _should_probe_link(url: str) -> bool:
    return platform_definition_for(destination_url=url).family == "external"


def _append_resolved_target(targets: list[ApplyTargetCandidate], candidate: ApplyTargetCandidate) -> None:
    for existing in targets:
        if existing.destination_url != candidate.destination_url or existing.target_type != candidate.target_type:
            continue
        existing.metadata = _merge_candidate_metadata(existing.metadata, candidate.metadata)
        return
    targets.append(candidate)


def _merge_candidate_metadata(existing: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    merged = {**existing, **new}
    source_urls = []
    for value in (existing.get("source_urls"), new.get("source_urls"), existing.get("source_url"), new.get("source_url")):
        if isinstance(value, str):
            candidates = [value]
        elif isinstance(value, list):
            candidates = [item for item in value if isinstance(item, str)]
        else:
            candidates = []
        for candidate in candidates:
            if candidate not in source_urls:
                source_urls.append(candidate)
    if source_urls:
        merged["source_urls"] = source_urls
        merged["source_url"] = source_urls[0]

    provenance_links: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for payload in (existing, new):
        for item in payload.get("provenance_links", []):
            if not isinstance(item, dict):
                continue
            key = (
                str(item.get("source_url") or ""),
                str(item.get("resolved_destination_url") or ""),
                str(item.get("link_kind") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            provenance_links.append(dict(item))
    if provenance_links:
        merged["provenance_links"] = provenance_links
    return merged
