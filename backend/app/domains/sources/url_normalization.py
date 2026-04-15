from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from app.domains.sources.models import JobSource


GREENHOUSE_GENERIC_SEGMENTS = {"embed", "job_board", "job-boards", "boards"}
GITHUB_HOSTS = {"github.com", "www.github.com", "raw.githubusercontent.com"}
GREENHOUSE_JOB_ID_PATTERN = re.compile(r"^\d+$")
LEVER_POSTING_ID_PATTERN = re.compile(r"^[0-9a-f-]{8,}$", re.IGNORECASE)


def _normalized_segments(url: str | None) -> list[str]:
    if not url:
        return []
    parsed = urlparse(url)
    return [segment.strip() for segment in parsed.path.split("/") if segment.strip()]


def derive_greenhouse_board_token(source: JobSource) -> str:
    configured = source.settings_json.get("board_token")
    if isinstance(configured, str) and configured.strip():
        return configured.strip().lower()

    token = derive_greenhouse_board_token_from_url(source.base_url)
    if token:
        return token

    raise ValueError("Greenhouse sources need a valid board URL or settings.board_token.")


def derive_lever_company_slug(source: JobSource) -> str:
    configured = source.settings_json.get("company_slug")
    if isinstance(configured, str) and configured.strip():
        return configured.strip().lower()

    slug = derive_lever_company_slug_from_url(source.base_url)
    if slug:
        return slug

    raise ValueError("Lever sources need a valid company URL or settings.company_slug.")


def derive_ashby_organization_host_token(source: JobSource) -> str:
    configured = source.settings_json.get("organization_host_token")
    if isinstance(configured, str) and configured.strip():
        return configured.strip().lower()

    for segment in _normalized_segments(source.base_url):
        return segment.lower()

    raise ValueError("Ashby sources need a valid jobs page URL or settings.organization_host_token.")


def derive_smartrecruiters_company_identifier(source: JobSource) -> str:
    configured = source.settings_json.get("company_identifier")
    if isinstance(configured, str) and configured.strip():
        return configured.strip()

    for segment in _normalized_segments(source.base_url):
        return segment

    raise ValueError("SmartRecruiters sources need a valid jobs page URL or settings.company_identifier.")


def resolve_github_raw_url(source: JobSource) -> str:
    raw_url = source.base_url or source.settings_json.get("raw_url")
    return normalize_github_curated_url(raw_url)


def derive_greenhouse_board_token_from_url(url: str | None) -> str | None:
    if not url:
        return None

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for_values = query.get("for") or query.get("board")
    if for_values:
        token = for_values[0].strip()
        if token:
            return token.lower()

    for segment in _normalized_segments(url):
        lowered = segment.lower()
        if lowered in GREENHOUSE_GENERIC_SEGMENTS or GREENHOUSE_JOB_ID_PATTERN.fullmatch(lowered):
            continue
        return lowered
    return None


def derive_greenhouse_job_post_id_from_url(url: str | None) -> str | None:
    for segment in reversed(_normalized_segments(url)):
        if GREENHOUSE_JOB_ID_PATTERN.fullmatch(segment):
            return segment
    return None


def derive_lever_company_slug_from_url(url: str | None) -> str | None:
    for segment in _normalized_segments(url):
        return segment.lower()
    return None


def derive_lever_posting_id_from_url(url: str | None) -> str | None:
    segments = _normalized_segments(url)
    for index, segment in enumerate(segments):
        if segment.lower() == "apply" and index > 0:
            return segments[index - 1]
        if LEVER_POSTING_ID_PATTERN.fullmatch(segment):
            return segment
    return None


def normalize_github_curated_url(value: str | None) -> str:
    if not value or not value.strip():
        raise ValueError("GitHub curated sources need a GitHub README URL.")

    trimmed = value.strip()
    parsed = urlparse(trimmed if "://" in trimmed else f"https://{trimmed}")
    host = parsed.netloc.lower()
    if host not in GITHUB_HOSTS:
        raise ValueError("GitHub curated sources need a GitHub README URL.")

    path_segments = [segment for segment in parsed.path.split("/") if segment]
    if host == "raw.githubusercontent.com":
        if len(path_segments) < 4:
            raise ValueError("GitHub curated sources need a valid raw README URL.")
        return f"https://raw.githubusercontent.com/{'/'.join(path_segments)}"

    if len(path_segments) < 2:
        raise ValueError("GitHub curated sources need a repo URL or README path.")

    owner, repo, *rest = path_segments
    if not rest:
        return f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/README.md"

    head = rest[0].lower()
    if head == "blob" and len(rest) >= 3:
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{'/'.join(rest[1:])}"
    if head == "raw" and len(rest) >= 2:
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{'/'.join(rest[1:])}"
    if rest[-1].lower().endswith(".md"):
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{'/'.join(rest)}"

    raise ValueError("GitHub curated sources need a repo URL or README path.")
