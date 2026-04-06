from app.integrations.linkedin.blockers import LinkedInAutomationError, classify_linkedin_exception


def test_linkedin_speed_limit_pages_map_to_cooldown_required() -> None:
    error = LinkedInAutomationError(
        code="daily_limit_reached",
        step="review",
        message="Daily limit reached.",
        page_text="You've exceeded the daily application limit. Try again tomorrow.",
    )

    decision = classify_linkedin_exception(error)

    assert decision.category == "cooldown_required"
    assert decision.status == "cooldown_required"
    assert decision.retryable is False


def test_linkedin_captcha_maps_to_human_action_required() -> None:
    error = LinkedInAutomationError(
        code="captcha_required",
        step="security-check",
        message="Captcha required.",
        page_text="Please complete the captcha to continue.",
    )

    decision = classify_linkedin_exception(error)

    assert decision.category == "human_action_required"
    assert decision.status == "action_needed"


def test_linkedin_selector_drift_maps_to_platform_changed() -> None:
    error = LinkedInAutomationError(
        code="selector_missing",
        step="form-fill",
        message="Expected selector missing from easy apply form.",
    )

    decision = classify_linkedin_exception(error)

    assert decision.category == "platform_changed"
    assert decision.status == "platform_changed"
