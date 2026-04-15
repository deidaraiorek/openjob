from app.integrations.smartrecruiters.client import parse_postings


def test_parse_smartrecruiters_postings_builds_direct_apply_candidates() -> None:
    payload = {
        "content": [
            {
                "id": "sr-posting-abc",
                "name": "Backend Engineer",
                "location": {"city": "San Francisco", "remote": False},
                "company": {"name": "Globex Corp"},
            }
        ]
    }

    records = parse_postings(payload, company_identifier="GlobexCorp")

    assert len(records) == 1
    record = records[0]
    assert record.external_job_id == "sr-posting-abc"
    assert record.company_name == "Globex Corp"
    assert record.title == "Backend Engineer"
    assert record.location == "San Francisco"
    assert record.apply_target_type == "smartrecruiters_apply"
    assert record.apply_url == "https://jobs.smartrecruiters.com/GlobexCorp/sr-posting-abc"
    assert record.metadata["company_identifier"] == "GlobexCorp"
    assert record.metadata["posting_id"] == "sr-posting-abc"


def test_parse_smartrecruiters_postings_marks_remote_location() -> None:
    payload = {
        "content": [
            {
                "id": "sr-remote-1",
                "name": "Remote Engineer",
                "location": {"city": "New York", "remote": True},
            }
        ]
    }

    records = parse_postings(payload, company_identifier="Acme")

    assert records[0].location == "Remote"


def test_parse_smartrecruiters_postings_falls_back_company_name_from_identifier() -> None:
    payload = {
        "content": [
            {
                "id": "sr-1",
                "name": "Data Analyst",
                "location": {},
            }
        ]
    }

    records = parse_postings(payload, company_identifier="some-company")

    assert records[0].company_name == "Some Company"


def test_parse_smartrecruiters_postings_uses_explicit_company_name() -> None:
    payload = {
        "content": [
            {
                "id": "sr-2",
                "name": "ML Engineer",
                "location": {},
            }
        ]
    }

    records = parse_postings(payload, company_identifier="AcmeLtd", company_name="Acme Ltd")

    assert records[0].company_name == "Acme Ltd"
