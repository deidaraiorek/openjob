from app.integrations.ashby.apply import build_submission_payload, parse_question_payload


def test_parse_ashby_apply_questions_builds_from_field_groups() -> None:
    payload = {
        "fieldGroups": [
            {
                "fields": [
                    {
                        "isRequired": True,
                        "field": {
                            "id": "_systemfield_name",
                            "title": "Full Name",
                            "type": "ShortText",
                            "selectableValues": [],
                        },
                    },
                    {
                        "isRequired": True,
                        "field": {
                            "id": "_systemfield_email",
                            "title": "Email",
                            "type": "Email",
                            "selectableValues": [],
                        },
                    },
                    {
                        "isRequired": False,
                        "field": {
                            "id": "work_auth",
                            "title": "Work Authorization",
                            "type": "Dropdown",
                            "selectableValues": [
                                {"label": "Yes, I am authorized"},
                                {"label": "No, I require sponsorship"},
                            ],
                        },
                    },
                ]
            }
        ]
    }

    questions = parse_question_payload(payload)

    assert len(questions) == 3
    assert questions[0].key == "_systemfield_name"
    assert questions[0].field_type == "input_text"
    assert questions[0].required is True
    assert questions[2].key == "work_auth"
    assert questions[2].field_type == "multi_value_single_select"
    assert questions[2].option_labels == ["Yes, I am authorized", "No, I require sponsorship"]


def test_build_ashby_submission_payload_structures_field_submissions() -> None:
    payload = {
        "fieldGroups": [
            {
                "fields": [
                    {
                        "isRequired": True,
                        "field": {"id": "_systemfield_name", "title": "Full Name", "type": "ShortText", "selectableValues": []},
                    },
                    {
                        "isRequired": True,
                        "field": {"id": "_systemfield_email", "title": "Email", "type": "Email", "selectableValues": []},
                    },
                ]
            }
        ]
    }

    questions = parse_question_payload(payload)
    submission = build_submission_payload(
        questions,
        {"_systemfield_name": "Jane Doe", "_systemfield_email": "jane@example.com"},
    )

    assert "fieldSubmissions" in submission
    field_map = {item["path"]: item["value"] for item in submission["fieldSubmissions"]}
    assert field_map["_systemfield_name"] == "Jane Doe"
    assert field_map["_systemfield_email"] == "jane@example.com"
