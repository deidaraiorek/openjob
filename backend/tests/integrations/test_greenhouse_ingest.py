from app.integrations.greenhouse.client import parse_jobs


def test_parse_greenhouse_jobs_builds_direct_apply_candidates() -> None:
    payload = {
        "company_name": "Acme",
        "jobs": [
            {
                "id": 123,
                "title": "Software Engineer I",
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/123",
                "location": {"name": "Remote"},
            },
        ],
    }

    records = parse_jobs(payload, board_token="acme")

    assert len(records) == 1
    record = records[0]
    assert record.external_job_id == "123"
    assert record.company_name == "Acme"
    assert record.apply_target_type == "greenhouse_apply"
    assert record.apply_url == "https://boards.greenhouse.io/acme/jobs/123"
    assert record.metadata["board_token"] == "acme"
    assert record.metadata["job_post_id"] == "123"
