from __future__ import annotations

import httpx


def fetch_markdown(url: str) -> str:
    response = httpx.get(url, timeout=30.0)
    response.raise_for_status()
    return response.text
