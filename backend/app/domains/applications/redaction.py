from __future__ import annotations

from typing import Any


def redact_payload(value: Any, key_hint: str | None = None) -> Any:
    if isinstance(value, dict):
        return {
            key: redact_payload(
                nested_value,
                key_hint=key,
            )
            for key, nested_value in value.items()
        }

    if isinstance(value, list):
        return [redact_payload(item, key_hint=key_hint) for item in value]

    if isinstance(value, (str, int, float, bool)) and value not in (None, ""):
        return "<redacted>"

    return value
