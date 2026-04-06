from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings


def _resolve_artifact_root(
    *,
    base_dir: str | Path | None = None,
    settings: Settings | None = None,
) -> Path:
    if base_dir is not None:
        return Path(base_dir)
    resolved_settings = settings or get_settings()
    return Path(resolved_settings.playwright_artifact_dir)


def _artifact_suffix(kind: str) -> str:
    suffix_map = {
        "screenshot": ".png",
        "page_html": ".html",
        "trace": ".zip",
        "storage_state": ".json",
    }
    return suffix_map.get(kind, ".txt")


def persist_artifacts(
    run_id: int,
    artifacts: dict[str, Any],
    *,
    base_dir: str | Path | None = None,
    settings: Settings | None = None,
) -> list[dict[str, str]]:
    if not artifacts:
        return []

    artifact_root = _resolve_artifact_root(base_dir=base_dir, settings=settings)
    run_directory = artifact_root / f"run-{run_id}"
    run_directory.mkdir(parents=True, exist_ok=True)

    persisted: list[dict[str, str]] = []
    for kind, content in artifacts.items():
        if content in (None, "", b""):
            continue

        path = run_directory / f"{kind}{_artifact_suffix(kind)}"
        if isinstance(content, bytes):
            path.write_bytes(content)
        elif isinstance(content, (dict, list)):
            path.write_text(json.dumps(content, indent=2), encoding="utf-8")
        else:
            path.write_text(str(content), encoding="utf-8")

        persisted.append({"kind": kind, "path": str(path)})

    return persisted
