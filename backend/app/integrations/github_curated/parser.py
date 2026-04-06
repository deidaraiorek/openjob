from __future__ import annotations

import re
from html import unescape

from app.domains.jobs.deduplication import DiscoveryCandidate

LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
HTML_LINK_PATTERN = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
ROW_PATTERN = re.compile(r"<tr>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
CELL_PATTERN = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL)
TAG_PATTERN = re.compile(r"<[^>]+>")


def _extract_link(cell: str) -> tuple[str, str | None]:
    html_match = HTML_LINK_PATTERN.search(cell)
    if html_match:
        return _strip_html(html_match.group(2)), html_match.group(1).strip()

    match = LINK_PATTERN.search(cell)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return _strip_html(cell), None


def _strip_html(value: str) -> str:
    normalized = value.replace("</br>", " ").replace("<br>", " ").replace("<br/>", " ").replace("<br />", " ")
    without_tags = TAG_PATTERN.sub(" ", normalized)
    return " ".join(unescape(without_tags).split())


def _parse_markdown_rows(markdown: str) -> list[DiscoveryCandidate]:
    records: list[DiscoveryCandidate] = []

    for line in markdown.splitlines():
        if not line.startswith("|") or "---" in line.lower():
            continue

        parts = [part.strip() for part in line.strip().strip("|").split("|")]
        if len(parts) < 4 or parts[0].lower() == "company":
            continue

        company_name, company_url = _extract_link(parts[0])
        title, listing_url = _extract_link(parts[1])
        location = parts[2] or None
        _, apply_url = _extract_link(parts[3])

        if not company_name or not title:
            continue

        records.append(
            DiscoveryCandidate(
                source_type="github_curated",
                external_job_id=listing_url or apply_url,
                company_name=company_name,
                title=title,
                location=location,
                listing_url=listing_url or company_url or apply_url or "",
                apply_url=apply_url,
                apply_target_type="external_link",
                raw_payload={"row": parts},
                metadata={"origin": "github_curated"},
            ),
        )

    return [record for record in records if record.listing_url]


def _parse_html_rows(markdown: str) -> list[DiscoveryCandidate]:
    records: list[DiscoveryCandidate] = []

    for row_html in ROW_PATTERN.findall(markdown):
        parts = [part.strip() for part in CELL_PATTERN.findall(row_html)]
        if len(parts) < 4:
            continue

        first_cell_text = _strip_html(parts[0]).lower()
        if first_cell_text == "company":
            continue

        company_name, company_url = _extract_link(parts[0])
        if company_name.startswith("↳"):
            company_name = company_name.removeprefix("↳").strip()
        title = _strip_html(parts[1])
        location = _strip_html(parts[2]) or None
        _, apply_url = _extract_link(parts[3])

        if not company_name or not title or not apply_url:
            continue

        records.append(
            DiscoveryCandidate(
                source_type="github_curated",
                external_job_id=apply_url,
                company_name=company_name,
                title=title,
                location=location,
                listing_url=apply_url,
                apply_url=apply_url,
                apply_target_type="external_link",
                raw_payload={"row_html": row_html},
                metadata={"origin": "github_curated"},
            ),
        )

    return records


def parse_markdown_jobs(markdown: str) -> list[DiscoveryCandidate]:
    markdown_records = _parse_markdown_rows(markdown)
    if markdown_records:
        return markdown_records

    return _parse_html_rows(markdown)
