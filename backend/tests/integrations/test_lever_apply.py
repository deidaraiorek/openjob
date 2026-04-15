from app.integrations.lever.apply import (
    build_submission_payload,
    fetch_question_payload,
    parse_question_payload,
    submit_application,
)


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


def test_fetch_lever_question_payload_uses_company_scoped_posting_url_when_slug_is_available(monkeypatch) -> None:
    calls: list[str] = []

    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"id": "posting-123"}

    def fake_get(url: str, timeout: float):
        calls.append(url)
        return DummyResponse()

    monkeypatch.setattr("app.integrations.lever.apply.httpx.get", fake_get)

    payload = fetch_question_payload("posting-123", "weride")

    assert payload == {"id": "posting-123"}
    assert calls == ["https://api.lever.co/v0/postings/weride/posting-123"]


def test_submit_lever_application_uses_company_scoped_posting_url_when_slug_is_available(monkeypatch) -> None:
    calls: list[tuple[str, dict, float]] = []

    class DummyResponse:
        content = b'{"ok": true}'

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"ok": True}

    def fake_post(url: str, json: dict, timeout: float):
        calls.append((url, json, timeout))
        return DummyResponse()

    monkeypatch.setattr("app.integrations.lever.apply.httpx.post", fake_post)

    payload = submit_application(
        "posting-123",
        {"fields": [{"name": "name", "value": "Dang"}]},
        company_slug="weride",
    )

    assert payload == {"ok": True}
    assert calls == [
        (
            "https://api.lever.co/v0/postings/weride/posting-123",
            {"fields": [{"name": "name", "value": "Dang"}]},
            30.0,
        )
    ]
