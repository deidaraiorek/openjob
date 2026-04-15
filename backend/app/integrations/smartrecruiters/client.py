from __future__ import annotations

import httpx

from app.domains.jobs.deduplication import DiscoveryCandidate


def fetch_postings(company_identifier: str) -> dict:
    response = httpx.get(
        f"https://api.smartrecruiters.com/v1/companies/{company_identifier}/postings",
        params={"status": "PUBLIC"},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def parse_postings(
    payload: dict,
    *,
    company_identifier: str,
    company_name: str | None = None,
) -> list[DiscoveryCandidate]:
    records: list[DiscoveryCandidate] = []

    content = payload.get("content", []) or []

    for posting in content:
        title = posting.get("name")
        if not title:
            continue

        posting_id = posting.get("id")
        location_obj = posting.get("location") or {}
        location = location_obj.get("city") or location_obj.get("region") or location_obj.get("country")
        if location_obj.get("remote"):
            location = "Remote"

        apply_url = f"https://jobs.smartrecruiters.com/{company_identifier}/{posting_id}"
        listing_url = apply_url

        resolved_company = company_name or posting.get("company", {}).get("name") if isinstance(posting.get("company"), dict) else company_name
        if not resolved_company:
            resolved_company = company_identifier.replace("-", " ").title()

        records.append(
            DiscoveryCandidate(
                source_type="smartrecruiters_board",
                external_job_id=str(posting_id) if posting_id else listing_url,
                company_name=resolved_company or "Unknown company",
                title=title,
                location=location,
                listing_url=listing_url,
                apply_url=apply_url,
                apply_target_type="smartrecruiters_apply",
                raw_payload=posting,
                metadata={
                    "origin": "smartrecruiters",
                    "company_identifier": company_identifier,
                    "posting_id": str(posting_id) if posting_id else None,
                },
            )
        )

    return [r for r in records if r.listing_url]
