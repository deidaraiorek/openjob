from __future__ import annotations

from dataclasses import dataclass


class RetryableApplyError(Exception):
    pass


class ActionNeededApplyError(Exception):
    pass


class TerminalApplyError(Exception):
    pass


@dataclass(slots=True)
class RetryDecision:
    status: str
    retryable: bool
    action_needed: bool


def classify_apply_exception(error: Exception) -> RetryDecision:
    if isinstance(error, RetryableApplyError):
        return RetryDecision(status="retry_scheduled", retryable=True, action_needed=False)
    if isinstance(error, ActionNeededApplyError):
        return RetryDecision(status="action_needed", retryable=False, action_needed=True)
    return RetryDecision(status="failed", retryable=False, action_needed=False)
