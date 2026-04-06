from __future__ import annotations

import re
from pathlib import Path

from app.config import Settings, get_settings


def _slugify(value: str) -> str:
    collapsed = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return collapsed or "default"


def build_profile_dir(
    account_id: int,
    source_key: str,
    *,
    settings: Settings | None = None,
) -> Path:
    resolved_settings = settings or get_settings()
    root = Path(resolved_settings.playwright_profile_dir)
    return root / f"account-{account_id}" / _slugify(source_key)


def ensure_profile_dir(
    account_id: int,
    source_key: str,
    *,
    settings: Settings | None = None,
) -> Path:
    path = build_profile_dir(account_id, source_key, settings=settings)
    path.mkdir(parents=True, exist_ok=True)
    return path
