from app.integrations.greenhouse.apply import build_submission_payload, parse_question_payload


def test_parse_greenhouse_apply_questions_and_build_payload() -> None:
    payload = {
        "questions": [
            {
                "label": "LinkedIn profile URL",
                "required": True,
                "fields": [{"name": "linkedin", "type": "input_text", "values": []}],
            },
            {
                "label": "Work authorization",
                "required": True,
                "fields": [
                    {
                        "name": "work_auth",
                        "type": "multi_value_single_select",
                        "values": [{"label": "Yes"}, {"label": "No"}],
                    }
                ],
            },
        ]
    }

    questions = parse_question_payload(payload)
    submission_payload = build_submission_payload(
        questions,
        {"linkedin": "https://linkedin.com/in/example", "work_auth": "Yes"},
    )

    assert [question.key for question in questions] == ["linkedin", "work_auth"]
    assert questions[1].option_labels == ["Yes", "No"]
    assert submission_payload == {
        "linkedin": "https://linkedin.com/in/example",
        "work_auth": "Yes",
    }
