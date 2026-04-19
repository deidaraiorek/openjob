from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domains.applications.retry_policy import RetryableApplyError, TerminalApplyError


TERMINAL_CODES = {"login_required", "login_failed", "captcha_required", "no_form_found", "submit_failed", "config_missing"}
RETRYABLE_CODES = {"timeout", "network_error", "max_steps_reached"}


class AIBrowserBlocker(Exception):
    def __init__(
        self,
        *,
        code: str,
        step: str,
        message: str,
        artifacts: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.step = step
        self.message = message
        self.artifacts = artifacts or {}


def classify_ai_browser_exception(error: Exception) -> Exception:
    if isinstance(error, AIBrowserBlocker):
        if error.code in TERMINAL_CODES:
            return TerminalApplyError(error.message)
        return RetryableApplyError(error.message)

    msg = str(error)
    lower = msg.lower()
    if "timeout" in lower or "timed out" in lower:
        return RetryableApplyError(msg)
    if "maxstepsreached" in type(error).__name__.lower() or "max steps" in lower:
        return RetryableApplyError(msg)
    if "network" in lower or "connection" in lower:
        return RetryableApplyError(msg)
    if "rate limit" in lower or "429" in lower or "ratelimit" in lower or "quota" in lower:
        return RetryableApplyError(msg)
    return TerminalApplyError(msg)
