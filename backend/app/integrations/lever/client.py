from __future__ import annotations

import httpx

from app.domains.jobs.deduplication import DiscoveryCandidate


def fetch_postings(company_slug: str) -> list[dict]:
    response = httpx.get(
        f"https://api.lever.co/v0/postings/{company_slug}?mode=json",
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def parse_postings(
    payload: list[dict],
    *,
    company_slug: str,
    company_name: str | None = None,
    api_key: str | None = None,
) -> list[DiscoveryCandidate]:
    records: list[DiscoveryCandidate] = []

    for posting in payload:
        title = posting.get("text")
        if not title:
            continue

        categories = posting.get("categories") or {}
        location = categories.get("location")
        listing_url = posting.get("hostedUrl")

        records.append(
            DiscoveryCandidate(
                source_type="lever_postings",
                external_job_id=posting.get("id") or listing_url,
                company_name=company_name or posting.get("company") or "Unknown company",
                title=title,
                location=location,
                listing_url=listing_url or "",
                apply_url=posting.get("applyUrl") or listing_url,
                apply_target_type="lever_apply",
                raw_payload=posting,
                metadata={
                    "origin": "lever",
                    "company_slug": company_slug,
                    "posting_id": posting.get("id"),
                    **({"api_key": api_key} if api_key else {}),
                },
            ),
        )

    return [record for record in records if record.listing_url]
