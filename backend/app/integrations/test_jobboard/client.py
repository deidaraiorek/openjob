from __future__ import annotations

import httpx

from app.domains.jobs.deduplication import DiscoveryCandidate

_JOBS = [
    {
        "id": "swe-backend-001",
        "title": "Senior Backend Engineer",
        "department": "Engineering",
        "location": "Remote",
        "type": "Full-time",
        "salary": "$160,000 – $200,000",
    },
    {
        "id": "swe-frontend-002",
        "title": "Frontend Engineer",
        "department": "Engineering",
        "location": "Remote",
        "type": "Full-time",
        "salary": "$130,000 – $160,000",
    },
    {
        "id": "ml-engineer-003",
        "title": "Machine Learning Engineer",
        "department": "AI Research",
        "location": "San Francisco, CA or Remote",
        "type": "Full-time",
        "salary": "$180,000 – $240,000",
    },
    {
        "id": "devrel-004",
        "title": "Developer Advocate",
        "department": "Developer Relations",
        "location": "Remote",
        "type": "Full-time",
        "salary": "$120,000 – $150,000",
    },
    {
        "id": "infra-engineer-005",
        "title": "Infrastructure Engineer",
        "department": "Platform",
        "location": "Remote",
        "type": "Full-time",
        "salary": "$150,000 – $190,000",
    },
]


def fetch_jobs(base_url: str) -> list[dict]:
    base_url = base_url.rstrip("/")
    try:
        response = httpx.get(f"{base_url}/api/jobs", timeout=5.0)
        response.raise_for_status()
        return response.json()
    except Exception:
        return _JOBS


def parse_jobs(jobs: list[dict], *, base_url: str, company_name: str = "NovaCorp") -> list[DiscoveryCandidate]:
    base_url = base_url.rstrip("/")
    candidates = []
    for job in jobs:
        job_id = job.get("id", "")
        apply_url = f"{base_url}/jobs/{job_id}/apply"
        candidates.append(
            DiscoveryCandidate(
                title=job.get("title", ""),
                company_name=company_name,
                location=job.get("location", ""),
                listing_url=apply_url,
                apply_url=apply_url,
                source_type="test_jobboard",
                apply_target_type="generic_career_page",
                metadata={
                    "platform_family": "generic_career_page",
                    "driver_family": "browser",
                    "compatibility_state": "browser_compatible",
                },
                raw_payload={
                    "id": job_id,
                    "title": job.get("title", ""),
                    "department": job.get("department", ""),
                    "location": job.get("location", ""),
                    "type": job.get("type", ""),
                    "salary": job.get("salary", ""),
                    "apply_url": apply_url,
                    "detail_url": f"{base_url}/jobs/{job_id}",
                },
            )
        )
    return candidates
