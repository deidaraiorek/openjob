from app.integrations.smartrecruiters.apply import build_submission_payload, parse_question_payload


def test_parse_smartrecruiters_apply_questions_builds_from_sections() -> None:
    payload = {
        "sections": [
            {
                "fields": [
                    {
                        "id": "firstName",
                        "label": "First Name",
                        "required": True,
                        "type": "TEXT",
                        "values": [],
                    },
                    {
                        "id": "lastName",
                        "label": "Last Name",
                        "required": True,
                        "type": "TEXT",
                        "values": [],
                    },
                    {
                        "id": "workAuthorization",
                        "label": "Work Authorization",
                        "required": False,
                        "type": "SINGLE_SELECT",
                        "values": [
                            {"label": "Authorized to work"},
                            {"label": "Requires sponsorship"},
                        ],
                    },
                ]
            }
        ]
    }

    questions = parse_question_payload(payload)

    assert len(questions) == 3
    assert questions[0].key == "firstName"
    assert questions[0].field_type == "input_text"
    assert questions[0].required is True
    assert questions[2].key == "workAuthorization"
    assert questions[2].field_type == "multi_value_single_select"
    assert questions[2].option_labels == ["Authorized to work", "Requires sponsorship"]


def test_build_smartrecruiters_submission_payload_structures_answers() -> None:
    payload = {
        "sections": [
            {
                "fields": [
                    {"id": "firstName", "label": "First Name", "required": True, "type": "TEXT", "values": []},
                    {"id": "email", "label": "Email", "required": True, "type": "TEXT", "values": []},
                ]
            }
        ]
    }

    questions = parse_question_payload(payload)
    submission = build_submission_payload(
        questions,
        {"firstName": "Jane", "email": "jane@example.com"},
    )

    assert "answers" in submission
    answer_map = {item["id"]: item["value"] for item in submission["answers"]}
    assert answer_map["firstName"] == "Jane"
    assert answer_map["email"] == "jane@example.com"


def test_build_smartrecruiters_submission_payload_skips_unanswered_questions() -> None:
    payload = {
        "sections": [
            {
                "fields": [
                    {"id": "firstName", "label": "First Name", "required": True, "type": "TEXT", "values": []},
                    {"id": "coverLetter", "label": "Cover Letter", "required": False, "type": "TEXTAREA", "values": []},
                ]
            }
        ]
    }

    questions = parse_question_payload(payload)
    submission = build_submission_payload(questions, {"firstName": "Jane"})

    ids = [item["id"] for item in submission["answers"]]
    assert "firstName" in ids
    assert "coverLetter" not in ids
