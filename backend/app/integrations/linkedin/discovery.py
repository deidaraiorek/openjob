from __future__ import annotations

from typing import Any

from app.domains.jobs.deduplication import DiscoveryCandidate


def parse_search_results(payload: dict[str, Any]) -> list[DiscoveryCandidate]:
    jobs = payload.get("jobs", [])
    candidates: list[DiscoveryCandidate] = []

    for job in jobs:
        listing_url = job.get("job_url") or job.get("listing_url")
        if not listing_url:
            continue

        easy_apply = bool(job.get("easy_apply"))
        external_job_id = job.get("job_posting_id") or job.get("id")
        apply_url = job.get("apply_url") or listing_url

        candidates.append(
            DiscoveryCandidate(
                source_type="linkedin_search",
                company_name=job.get("company_name", "Unknown company"),
                title=job.get("title", "Unknown title"),
                location=job.get("location"),
                listing_url=listing_url,
                apply_url=apply_url,
                external_job_id=str(external_job_id) if external_job_id is not None else None,
                apply_target_type="linkedin_easy_apply" if easy_apply else "external_link",
                raw_payload=job,
                metadata={
                    "linkedin_job_id": str(external_job_id) if external_job_id is not None else None,
                    "easy_apply": easy_apply,
                },
            )
        )

    return candidates
