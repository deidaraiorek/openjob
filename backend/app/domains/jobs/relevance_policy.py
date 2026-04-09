from __future__ import annotations

from typing import Literal

from app.domains.role_profiles.models import RoleProfile

LevelBand = Literal["early_career", "mid", "senior_plus", "unknown"]
Track = Literal["individual_contributor", "managerial", "unknown"]

_EARLY_CAREER_PHRASES = (
    "new grad",
    "entry level",
    "entry-level",
    "junior",
    "associate",
    "graduate",
    "campus",
    "university grad",
    "recent grad",
)
_SENIOR_PLUS_PHRASES = (
    "senior",
    "staff",
    "principal",
    "lead",
    "manager",
    "director",
    "head of",
)
_MANAGERIAL_PHRASES = (
    "manager",
    "director",
    "head of",
    "vp ",
    "vice president",
)


def _normalize_prompt(prompt: str | None) -> str:
    return " ".join((prompt or "").lower().replace("-", " ").replace("/", " ").split())


def derive_profile_hints(profile: RoleProfile | None) -> dict[str, str | bool]:
    normalized_prompt = _normalize_prompt(profile.prompt if profile else None)
    if not normalized_prompt:
        return {
            "target_level_band": "unknown",
            "target_track": "unknown",
            "prompt_mentions_entry_level": False,
        }

    level_band: LevelBand = "mid"
    if any(phrase in normalized_prompt for phrase in _EARLY_CAREER_PHRASES):
        level_band = "early_career"
    elif any(phrase in normalized_prompt for phrase in _SENIOR_PLUS_PHRASES):
        level_band = "senior_plus"

    track: Track = "individual_contributor"
    if any(phrase in normalized_prompt for phrase in _MANAGERIAL_PHRASES):
        track = "managerial"

    if normalized_prompt == "":
        level_band = "unknown"
        track = "unknown"

    return {
        "target_level_band": level_band,
        "target_track": track,
        "prompt_mentions_entry_level": level_band == "early_career",
    }


def build_role_context_for_screening(role_prompt: str | None, hints: dict[str, str | bool]) -> str:
    normalized = _normalize_prompt(role_prompt)
    if not normalized:
        return ""

    level_band = hints.get("target_level_band", "unknown")

    if level_band == "early_career":
        level_desc = (
            "early-career level (new grad, junior, associate, graduate, entry level, level 1, L1). "
            "Treat all early-career level wording variants as compatible — do not reject a title solely because it uses "
            "a different entry-level label than the user's prompt."
        )
    elif level_band == "senior_plus":
        level_desc = "senior level (senior, staff, principal, lead, or above)."
    else:
        level_desc = "mid-level or general individual-contributor level."

    return (
        f"The user is targeting: '{normalized}' at {level_desc}"
    )


def build_decision_policy(profile: RoleProfile | None) -> dict[str, str | bool]:
    hints = derive_profile_hints(profile)
    return {
        "title_screening_mode": "pass_or_reject",
        "passed_title_is_strong_positive_signal": True,
        "accept_adjacent_level_variants": hints["target_level_band"] == "early_career",
        "accept_role_family_variants": True,
        "treat_specialization_modifiers_as_neutral": True,
        "require_clear_evidence_for_seniority_mismatch": True,
        "prefer_match_over_review_when_context_is_consistent": True,
    }
