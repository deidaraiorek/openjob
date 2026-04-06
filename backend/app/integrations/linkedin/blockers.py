from __future__ import annotations

from dataclasses import dataclass
from typing import Any


COOLDOWN_MARKERS = (
    "application limit",
    "try again tomorrow",
    "too many applications",
    "you've exceeded",
)
HUMAN_ACTION_MARKERS = (
    "captcha",
    "verify your identity",
    "security verification",
    "enter the code we sent",
    "two-step verification",
    "sign in",
)
PLATFORM_CHANGED_MARKERS = (
    "selector missing",
    "unexpected layout",
    "page structure changed",
)

RETRYABLE_CODES = {"navigation_timeout", "temporary_network", "browser_start_failed"}
COOLDOWN_CODES = {"easy_apply_limit", "daily_limit_reached", "cooldown_required"}
HUMAN_ACTION_CODES = {"captcha_required", "mfa_required", "login_required", "security_checkpoint"}
PLATFORM_CHANGED_CODES = {"selector_missing", "unexpected_dom", "runner_not_configured"}


class LinkedInAutomationError(Exception):
    def __init__(
        self,
        *,
        code: str,
        step: str,
        message: str,
        artifacts: dict[str, Any] | None = None,
        page_text: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.step = step
        self.message = message
        self.artifacts = artifacts or {}
        self.page_text = page_text or ""


@dataclass(slots=True)
class LinkedInBlockerDecision:
    category: str
    status: str
    retryable: bool
    step: str | None
    message: str
    code: str | None


def _contains_marker(page_text: str, markers: tuple[str, ...]) -> bool:
    lowered = page_text.lower()
    return any(marker in lowered for marker in markers)


def classify_linkedin_exception(error: Exception) -> LinkedInBlockerDecision:
    if isinstance(error, TimeoutError):
        return LinkedInBlockerDecision(
            category="retryable_transient",
            status="retry_scheduled",
            retryable=True,
            step=None,
            message=str(error),
            code="timeout",
        )

    if not isinstance(error, LinkedInAutomationError):
        return LinkedInBlockerDecision(
            category="human_action_required",
            status="action_needed",
            retryable=False,
            step=None,
            message=str(error),
            code=None,
        )

    if error.code in RETRYABLE_CODES:
        return LinkedInBlockerDecision(
            category="retryable_transient",
            status="retry_scheduled",
            retryable=True,
            step=error.step,
            message=error.message,
            code=error.code,
        )

    if error.code in COOLDOWN_CODES or _contains_marker(error.page_text, COOLDOWN_MARKERS):
        return LinkedInBlockerDecision(
            category="cooldown_required",
            status="cooldown_required",
            retryable=False,
            step=error.step,
            message=error.message,
            code=error.code,
        )

    if error.code in HUMAN_ACTION_CODES or _contains_marker(error.page_text, HUMAN_ACTION_MARKERS):
        return LinkedInBlockerDecision(
            category="human_action_required",
            status="action_needed",
            retryable=False,
            step=error.step,
            message=error.message,
            code=error.code,
        )

    if error.code in PLATFORM_CHANGED_CODES or _contains_marker(error.page_text, PLATFORM_CHANGED_MARKERS):
        return LinkedInBlockerDecision(
            category="platform_changed",
            status="platform_changed",
            retryable=False,
            step=error.step,
            message=error.message,
            code=error.code,
        )

    return LinkedInBlockerDecision(
        category="human_action_required",
        status="action_needed",
        retryable=False,
        step=error.step,
        message=error.message,
        code=error.code,
    )
