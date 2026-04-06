from __future__ import annotations

import re
from dataclasses import dataclass


STOP_TOKENS = {"role", "roles", "job", "jobs", "position", "positions", "opportunity", "opportunities"}
ROMAN_TO_ARABIC = {
    "i": "1",
    "ii": "2",
    "iii": "3",
    "iv": "4",
}
ARABIC_TO_ROMAN = {value: key for key, value in ROMAN_TO_ARABIC.items()}


def _normalize_separators(value: str) -> str:
    lowered = value.lower()
    lowered = re.sub(r"[()]", " ", lowered)
    lowered = re.sub(r"[/_,\-]+", " ", lowered)
    lowered = re.sub(r"[,:;]+", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


def normalize_title_tokens(value: str) -> list[str]:
    normalized = _normalize_separators(value)
    tokens = re.findall(r"[a-z0-9]+", normalized)
    collapsed = [ROMAN_TO_ARABIC.get(token, token) for token in tokens if token not in STOP_TOKENS]
    return collapsed


def normalized_title_key(value: str) -> str:
    return " ".join(normalize_title_tokens(value))


def normalized_title_token_set(value: str) -> tuple[str, ...]:
    return tuple(sorted(normalize_title_tokens(value)))


@dataclass(frozen=True, slots=True)
class TitleMatchResult:
    matched: bool
    normalized_title: str
    matched_titles: list[str]
    summary: str


def match_title_against_catalog(title: str, catalog: list[str]) -> TitleMatchResult:
    normalized_title = normalized_title_key(title)
    title_token_set = normalized_title_token_set(title)
    matched_titles: list[str] = []

    for candidate in catalog:
        candidate_key = normalized_title_key(candidate)
        if not candidate_key:
            continue
        if candidate_key == normalized_title or normalized_title_token_set(candidate) == title_token_set:
            matched_titles.append(candidate)

    if matched_titles:
        return TitleMatchResult(
            matched=True,
            normalized_title=normalized_title,
            matched_titles=sorted(set(matched_titles)),
            summary="Title matched the saved title catalog and is eligible for AI review.",
        )

    return TitleMatchResult(
        matched=False,
        normalized_title=normalized_title,
        matched_titles=[],
        summary="Title does not match the saved title catalog, so it was rejected before AI review.",
    )
