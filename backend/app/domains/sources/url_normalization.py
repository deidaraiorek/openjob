from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from app.domains.sources.models import JobSource


GREENHOUSE_GENERIC_SEGMENTS = {"embed", "job_board", "job-boards", "boards"}


def _normalized_segments(url: str | None) -> list[str]:
    if not url:
        return []
    parsed = urlparse(url)
    return [segment.strip() for segment in parsed.path.split("/") if segment.strip()]


def derive_greenhouse_board_token(source: JobSource) -> str:
    configured = source.settings_json.get("board_token")
    if isinstance(configured, str) and configured.strip():
        return configured.strip().lower()

    if source.base_url:
        parsed = urlparse(source.base_url)
        query = parse_qs(parsed.query)
        for_values = query.get("for") or query.get("board")
        if for_values:
            token = for_values[0].strip()
            if token:
                return token.lower()

        for segment in _normalized_segments(source.base_url):
            lowered = segment.lower()
            if lowered in GREENHOUSE_GENERIC_SEGMENTS:
                continue
            return lowered

    raise ValueError("Greenhouse sources need a valid board URL or settings.board_token.")


def derive_lever_company_slug(source: JobSource) -> str:
    configured = source.settings_json.get("company_slug")
    if isinstance(configured, str) and configured.strip():
        return configured.strip().lower()

    for segment in _normalized_segments(source.base_url):
        return segment.lower()

    raise ValueError("Lever sources need a valid company URL or settings.company_slug.")


def resolve_github_raw_url(source: JobSource) -> str:
    raw_url = source.base_url or source.settings_json.get("raw_url")
    if isinstance(raw_url, str) and raw_url.strip():
        return raw_url.strip()
    raise ValueError("GitHub curated sources need a raw README URL.")
