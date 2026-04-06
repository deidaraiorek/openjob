from app.integrations.lever.client import parse_postings


def test_parse_lever_postings_builds_direct_apply_candidates() -> None:
    payload = [
        {
            "id": "lever-123",
            "text": "Backend Engineer I",
            "hostedUrl": "https://jobs.lever.co/acme/lever-123",
            "applyUrl": "https://jobs.lever.co/acme/lever-123/apply",
            "categories": {"location": "San Francisco, CA"},
        },
    ]

    records = parse_postings(payload, company_slug="acme", company_name="Acme")

    assert len(records) == 1
    record = records[0]
    assert record.external_job_id == "lever-123"
    assert record.company_name == "Acme"
    assert record.title == "Backend Engineer I"
    assert record.apply_target_type == "lever_apply"
    assert record.metadata["company_slug"] == "acme"
    assert record.metadata["posting_id"] == "lever-123"
