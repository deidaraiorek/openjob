from app.integrations.ashby.client import parse_postings


def test_parse_ashby_postings_builds_direct_apply_candidates() -> None:
    postings = [
        {
            "id": "abc-123",
            "title": "Software Engineer",
            "locationName": "Remote",
            "jobUrl": "https://jobs.ashbyhq.com/acme/abc-123",
            "isListed": True,
            "publishedAt": "2026-04-01T00:00:00Z",
        }
    ]

    records = parse_postings(postings, organization_host_token="acme", company_name="Acme Corp")

    assert len(records) == 1
    record = records[0]
    assert record.external_job_id == "abc-123"
    assert record.company_name == "Acme Corp"
    assert record.title == "Software Engineer"
    assert record.location == "Remote"
    assert record.apply_target_type == "ashby_apply"
    assert record.apply_url == "https://jobs.ashbyhq.com/acme/abc-123"
    assert record.metadata["organization_host_token"] == "acme"
    assert record.metadata["job_posting_id"] == "abc-123"


def test_parse_ashby_postings_skips_unlisted_jobs_without_published_date() -> None:
    postings = [
        {
            "id": "hidden-1",
            "title": "Internal Role",
            "isListed": False,
            "publishedAt": None,
            "jobUrl": "https://jobs.ashbyhq.com/acme/hidden-1",
        },
        {
            "id": "pub-1",
            "title": "Published Role",
            "isListed": False,
            "publishedAt": "2026-04-01T00:00:00Z",
            "jobUrl": "https://jobs.ashbyhq.com/acme/pub-1",
        },
    ]

    records = parse_postings(postings, organization_host_token="acme")

    assert len(records) == 1
    assert records[0].external_job_id == "pub-1"


def test_parse_ashby_postings_falls_back_company_name_from_token() -> None:
    postings = [
        {
            "id": "xyz-1",
            "title": "Data Engineer",
            "isListed": True,
            "publishedAt": "2026-04-01T00:00:00Z",
            "jobUrl": "https://jobs.ashbyhq.com/some-company/xyz-1",
        }
    ]

    records = parse_postings(postings, organization_host_token="some-company")

    assert records[0].company_name == "Some Company"
