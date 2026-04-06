from app.integrations.github_curated.parser import parse_markdown_jobs


def test_parse_markdown_jobs_extracts_company_title_location_and_apply_url() -> None:
    markdown = """
| Company | Role | Location | Application |
| --- | --- | --- | --- |
| [Acme](https://acme.example) | [Software Engineer I](https://simplify.jobs/jobs/acme-1) | Remote | [Apply](https://boards.greenhouse.io/acme/jobs/123) |
"""

    records = parse_markdown_jobs(markdown)

    assert len(records) == 1
    record = records[0]
    assert record.company_name == "Acme"
    assert record.title == "Software Engineer I"
    assert record.location == "Remote"
    assert record.listing_url == "https://simplify.jobs/jobs/acme-1"
    assert record.apply_url == "https://boards.greenhouse.io/acme/jobs/123"


def test_parse_markdown_jobs_extracts_jobs_from_html_tables() -> None:
    markdown = """
<table>
<thead>
<tr>
<th>Company</th>
<th>Role</th>
<th>Location</th>
<th>Application</th>
</tr>
</thead>
<tbody>
<tr>
<td><strong><a href="https://simplify.jobs/c/Acme">Acme</a></strong></td>
<td>Software Engineer 1</td>
<td>Seattle, WA</td>
<td><div align="center"><a href="https://boards.greenhouse.io/acme/jobs/123"><img alt="Apply"></a></div></td>
</tr>
</tbody>
</table>
"""

    records = parse_markdown_jobs(markdown)

    assert len(records) == 1
    record = records[0]
    assert record.company_name == "Acme"
    assert record.title == "Software Engineer 1"
    assert record.location == "Seattle, WA"
    assert record.listing_url == "https://boards.greenhouse.io/acme/jobs/123"
    assert record.apply_url == "https://boards.greenhouse.io/acme/jobs/123"
