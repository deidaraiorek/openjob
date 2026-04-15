from __future__ import annotations

import httpx

from app.domains.jobs.deduplication import DiscoveryCandidate


def fetch_job_postings(organization_host_token: str) -> list[dict]:
    response = httpx.post(
        "https://api.ashbyhq.com/jobPosting.list",
        json={"organizationHostedJobsPageName": organization_host_token},
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    return data.get("results", [])


def fetch_application_form(job_posting_id: str) -> dict:
    response = httpx.post(
        "https://api.ashbyhq.com/applicationForm.info",
        json={"jobPostingId": job_posting_id},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json().get("results", {})


def parse_postings(
    postings: list[dict],
    *,
    organization_host_token: str,
    company_name: str | None = None,
) -> list[DiscoveryCandidate]:
    records: list[DiscoveryCandidate] = []

    for posting in postings:
        if not posting.get("isListed") and not posting.get("publishedAt"):
            continue

        title = posting.get("title")
        if not title:
            continue

        location = posting.get("locationName") or posting.get("location", {}).get("name") if isinstance(posting.get("location"), dict) else posting.get("locationName")
        job_posting_id = posting.get("id")
        apply_url = posting.get("jobUrl") or f"https://jobs.ashbyhq.com/{organization_host_token}/{job_posting_id}"
        listing_url = apply_url

        resolved_company = company_name or posting.get("department", {}).get("name") if isinstance(posting.get("department"), dict) else company_name
        if not resolved_company:
            resolved_company = organization_host_token.replace("-", " ").title()

        records.append(
            DiscoveryCandidate(
                source_type="ashby_board",
                external_job_id=str(job_posting_id) if job_posting_id else listing_url,
                company_name=resolved_company or "Unknown company",
                title=title,
                location=location,
                listing_url=listing_url,
                apply_url=apply_url,
                apply_target_type="ashby_apply",
                raw_payload=posting,
                metadata={
                    "origin": "ashby",
                    "organization_host_token": organization_host_token,
                    "job_posting_id": str(job_posting_id) if job_posting_id else None,
                },
            )
        )

    return [r for r in records if r.listing_url]
