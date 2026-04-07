from app.domains.accounts.service import ensure_account
from app.domains.jobs.relevance_policy import build_decision_policy, derive_profile_hints
from app.domains.role_profiles.models import RoleProfile


def test_derive_profile_hints_detects_early_career_ic_prompt(db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    profile = RoleProfile(
        account_id=account.id,
        prompt="new grad software engineer",
        generated_titles=[],
        generated_keywords=[],
    )

    hints = derive_profile_hints(profile)

    assert hints["target_level_band"] == "early_career"
    assert hints["target_track"] == "individual_contributor"
    assert hints["prompt_mentions_entry_level"] is True


def test_build_decision_policy_prefers_adjacent_level_variants_for_early_career(db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    profile = RoleProfile(
        account_id=account.id,
        prompt="new grad software engineer",
        generated_titles=[],
        generated_keywords=[],
    )

    policy = build_decision_policy(profile)

    assert policy["title_screening_mode"] == "pass_or_reject"
    assert policy["passed_title_is_strong_positive_signal"] is True
    assert policy["accept_adjacent_level_variants"] is True
