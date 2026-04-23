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
