from __future__ import annotations

import httpx

from app.domains.jobs.deduplication import DiscoveryCandidate


def fetch_jobs(board_token: str) -> dict:
    response = httpx.get(
        f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs",
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def parse_jobs(payload: dict, *, board_token: str, api_key: str | None = None) -> list[DiscoveryCandidate]:
    company_name = payload.get("company_name")
    jobs = payload.get("jobs", [])
    records: list[DiscoveryCandidate] = []

    for job in jobs:
        title = job.get("title")
        if not title:
            continue

        location = None
        if isinstance(job.get("location"), dict):
            location = job["location"].get("name")

        absolute_url = job.get("absolute_url")
        records.append(
            DiscoveryCandidate(
                source_type="greenhouse_board",
                external_job_id=str(job.get("id")) if job.get("id") is not None else absolute_url,
                company_name=job.get("company_name") or company_name or "Unknown company",
                title=title,
                location=location,
                listing_url=absolute_url or "",
                apply_url=absolute_url,
                apply_target_type="greenhouse_apply",
                raw_payload=job,
                metadata={
                    "origin": "greenhouse",
                    "board_token": board_token,
                    "job_post_id": str(job.get("id")) if job.get("id") is not None else None,
                    **({"api_key": api_key} if api_key else {}),
                },
            ),
        )

    return [record for record in records if record.listing_url]
