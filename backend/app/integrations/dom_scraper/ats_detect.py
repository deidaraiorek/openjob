from __future__ import annotations

import re
from urllib.parse import urlparse


_ATS_URL_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"boards\.greenhouse\.io", re.I), "greenhouse"),
    (re.compile(r"job-boards\.greenhouse\.io", re.I), "greenhouse"),
    (re.compile(r"jobs\.lever\.co", re.I), "lever"),
    (re.compile(r"app\.ashbyhq\.com/jobs", re.I), "ashby"),
    (re.compile(r"jobs\.ashbyhq\.com", re.I), "ashby"),
    (re.compile(r"myworkdayjobs\.com", re.I), "workday"),
    (re.compile(r"wd\d+\.myworkdayjobs\.com", re.I), "workday"),
    (re.compile(r"smartrecruiters\.com/apply", re.I), "smartrecruiters"),
    (re.compile(r"jobs\.smartrecruiters\.com", re.I), "smartrecruiters"),
    (re.compile(r"icims\.com", re.I), "icims"),
    (re.compile(r"careers\.jobvite\.com", re.I), "jobvite"),
    (re.compile(r"jobs\.jobvite\.com", re.I), "jobvite"),
]


def detect_ats(url: str) -> str | None:
    for pattern, ats in _ATS_URL_PATTERNS:
        if pattern.search(url):
            return ats
    return None


def is_supported(url: str) -> bool:
    return detect_ats(url) is not None


def resolve_apply_url(url: str) -> str:
    """Transform a job listing URL to its direct application form URL if needed."""
    ats = detect_ats(url)
    if ats == "ashby":
        # jobs.ashbyhq.com/<company>/<job-id> → jobs.ashbyhq.com/<company>/<job-id>/application
        # app.ashbyhq.com/jobs/<company>/<job-id> → same pattern
        if not url.rstrip("/").endswith("/application"):
            return url.rstrip("/") + "/application"
    if ats == "lever":
        # jobs.lever.co/<company>/<job-id> → jobs.lever.co/<company>/<job-id>/apply
        if not url.rstrip("/").endswith("/apply"):
            return url.rstrip("/") + "/apply"
    return url
