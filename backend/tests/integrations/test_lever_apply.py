from app.integrations.lever.apply import build_submission_payload, parse_question_payload


def test_parse_lever_apply_questions_and_build_payload() -> None:
    payload = {
        "personalInformation": [
            {"name": "name", "text": "Full name", "type": "text", "required": True},
        ],
        "customQuestions": [
            {
                "text": "Portfolio URL",
                "required": True,
                "fields": [{"name": "portfolio", "text": "Portfolio URL", "type": "text", "required": True}],
            }
        ],
        "urls": [
            {"name": "linkedin", "text": "LinkedIn profile", "type": "text", "required": False},
        ],
    }

    questions = parse_question_payload(payload)
    submission_payload = build_submission_payload(
        questions,
        {
            "name": "Dang Pham",
            "portfolio": "https://example.com",
            "linkedin": "https://linkedin.com/in/example",
        },
    )

    assert [question.key for question in questions] == ["name", "portfolio", "linkedin"]
    assert submission_payload == {
        "fields": [
            {"name": "name", "value": "Dang Pham"},
            {"name": "portfolio", "value": "https://example.com"},
            {"name": "linkedin", "value": "https://linkedin.com/in/example"},
        ]
    }
