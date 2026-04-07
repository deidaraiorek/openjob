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
TOKEN_ALIASES = {
    "developer": "engineer",
    "developers": "engineer",
    "engineers": "engineer",
    "grads": "grad",
}
ENTRY_LEVEL_TOKENS = {"new", "grad", "early", "career", "entry", "level", "associate", "university", "campus"}
SENIORITY_BLOCKERS = {"senior", "sr", "staff", "principal"}
LEVEL_TOKENS = {"1", "2", "3", "4"}


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
    collapsed: list[str] = []
    for token in tokens:
        if token in STOP_TOKENS:
            continue
        canonical = ROMAN_TO_ARABIC.get(token, token)
        canonical = TOKEN_ALIASES.get(canonical, canonical)
        collapsed.append(canonical)
    return collapsed


def normalized_title_key(value: str) -> str:
    return " ".join(normalize_title_tokens(value))


def normalized_title_token_set(value: str) -> tuple[str, ...]:
    return tuple(sorted(normalize_title_tokens(value)))


@dataclass(frozen=True, slots=True)
class TitleAnalysis:
    normalized_title: str
    token_set: frozenset[str]
    core_token_set: frozenset[str]
    level_value: int | None
    level_signals: tuple[str, ...]
    has_explicit_seniority: bool


@dataclass(frozen=True, slots=True)
class TitleMatchResult:
    matched: bool
    normalized_title: str
    normalized_core_title: str | None
    matched_titles: list[str]
    matched_level_tokens: list[str]
    ignored_modifier_tokens: list[str]
    reject_reason: str | None
    summary: str


def _detect_level_signals(tokens: list[str]) -> list[str]:
    signals: list[str] = []

    def add(signal: str) -> None:
        if signal not in signals:
            signals.append(signal)

    for index, token in enumerate(tokens):
        next_token = tokens[index + 1] if index + 1 < len(tokens) else None
        if token == "1":
            add("1")
        if token == "associate":
            add("associate")
        if token == "new" and next_token == "grad":
            add("new grad")
        if token == "early" and next_token == "career":
            add("early career")
        if token == "entry" and next_token == "level":
            add("entry level")
        if token == "university" and next_token == "grad":
            add("university grad")

    return signals


def _core_tokens(tokens: list[str]) -> frozenset[str]:
    return frozenset(
        token
        for token in tokens
        if token not in LEVEL_TOKENS and token not in ENTRY_LEVEL_TOKENS and token not in SENIORITY_BLOCKERS
    )


def _analyze_title(value: str) -> TitleAnalysis:
    tokens = normalize_title_tokens(value)
    numeric_levels = [int(token) for token in tokens if token in LEVEL_TOKENS]
    return TitleAnalysis(
        normalized_title=" ".join(tokens),
        token_set=frozenset(tokens),
        core_token_set=_core_tokens(tokens),
        level_value=max(numeric_levels) if numeric_levels else None,
        level_signals=tuple(_detect_level_signals(tokens)),
        has_explicit_seniority=any(token in SENIORITY_BLOCKERS for token in tokens),
    )


def _is_exact_match(title: TitleAnalysis, candidate: TitleAnalysis) -> bool:
    return (
        title.normalized_title == candidate.normalized_title
        or title.token_set == candidate.token_set
    )


def _core_tokens_match(title: TitleAnalysis, candidate: TitleAnalysis) -> bool:
    if not title.core_token_set or not candidate.core_token_set:
        return False
    shared = title.core_token_set & candidate.core_token_set
    smaller = min(len(title.core_token_set), len(candidate.core_token_set))
    if smaller < 2:
        return shared == title.core_token_set == candidate.core_token_set
    return len(shared) >= 2 and (
        shared == title.core_token_set or shared == candidate.core_token_set
    )


def _resolve_level_conflict(title: TitleAnalysis, candidate: TitleAnalysis) -> str | None:
    if candidate.level_value is not None and title.level_value is not None and title.level_value != candidate.level_value:
        return "seniority_mismatch"
    if title.level_value is not None and title.level_value > 1 and candidate.level_signals:
        return "seniority_mismatch"
    if title.has_explicit_seniority and (candidate.level_value == 1 or candidate.level_signals):
        return "seniority_mismatch"
    return None


def _success_summary(modifiers: list[str]) -> str:
    if not modifiers:
        return "Title matched the saved title catalog and is eligible for AI review."
    return (
        "Title matched the saved title catalog after ignoring extra modifiers "
        f"({', '.join(modifiers)}), so it is eligible for AI review."
    )


def match_title_against_catalog(title: str, catalog: list[str]) -> TitleMatchResult:
    analyzed_title = _analyze_title(title)
    matched_titles: list[str] = []
    ignored_modifier_tokens: set[str] = set()
    reject_reasons: list[str] = []

    for candidate in catalog:
        analyzed_candidate = _analyze_title(candidate)
        if not analyzed_candidate.normalized_title:
            continue

        if _is_exact_match(analyzed_title, analyzed_candidate):
            matched_titles.append(candidate)
            continue

        if not _core_tokens_match(analyzed_title, analyzed_candidate):
            reject_reasons.append("family_mismatch")
            continue

        level_conflict = _resolve_level_conflict(analyzed_title, analyzed_candidate)
        if level_conflict is not None:
            reject_reasons.append(level_conflict)
            continue

        matched_titles.append(candidate)
        ignored_modifier_tokens.update(
            analyzed_title.core_token_set - analyzed_candidate.core_token_set,
        )

    if matched_titles:
        normalized_core_title = " ".join(sorted(analyzed_title.core_token_set)) or None
        modifiers = sorted(ignored_modifier_tokens)
        return TitleMatchResult(
            matched=True,
            normalized_title=analyzed_title.normalized_title,
            normalized_core_title=normalized_core_title,
            matched_titles=sorted(set(matched_titles)),
            matched_level_tokens=sorted(set(analyzed_title.level_signals)),
            ignored_modifier_tokens=modifiers,
            reject_reason=None,
            summary=_success_summary(modifiers),
        )

    reject_reason = "family_mismatch"
    if reject_reasons and all(reason == "seniority_mismatch" for reason in reject_reasons):
        reject_reason = "seniority_mismatch"

    summary = "Title does not match the saved title catalog's role family."
    if reject_reason == "seniority_mismatch":
        summary = "Title has an explicit seniority mismatch with the saved title catalog."

    normalized_core_title = " ".join(sorted(analyzed_title.core_token_set)) or None
    return TitleMatchResult(
        matched=False,
        normalized_title=analyzed_title.normalized_title,
        normalized_core_title=normalized_core_title,
        matched_titles=[],
        matched_level_tokens=sorted(set(analyzed_title.level_signals)),
        ignored_modifier_tokens=[],
        reject_reason=reject_reason,
        summary=summary,
    )
