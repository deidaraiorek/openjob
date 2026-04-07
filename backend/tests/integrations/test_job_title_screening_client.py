from app.integrations.openai.job_title_screening import classify_job_titles


class _FakeCompletions:
    def __init__(self, content: str) -> None:
        self._content = content

    def create(self, **kwargs):
        class _Message:
            content = self._content

        class _Choice:
            message = _Message()

        class _Response:
            choices = [_Choice()]

        return _Response()


class _FakeChat:
    def __init__(self, content: str) -> None:
        self.completions = _FakeCompletions(content)


class _FakeClient:
    def __init__(self, content: str) -> None:
        self.chat = _FakeChat(content)


def test_classify_job_titles_parses_structured_batch_json() -> None:
    result = classify_job_titles(
        "new grad software engineer",
        ["Software Engineer - AI Platform", "Data Engineer"],
        client=_FakeClient(
            """
            {
              "results": [
                {
                  "title_index": 0,
                  "decision": "pass",
                  "summary": "Matches the target software engineering role."
                },
                {
                  "title_index": 1,
                  "decision": "reject",
                  "summary": "Outside the target role family."
                }
              ]
            }
            """
        ),
    )

    assert result.source == "ai"
    assert [item.decision for item in result.items] == ["pass", "reject"]


def test_classify_job_titles_marks_missing_index_as_pass() -> None:
    result = classify_job_titles(
        "new grad software engineer",
        ["Software Engineer - AI Platform", "Data Engineer"],
        client=_FakeClient(
            """
            {
              "results": [
                {
                  "title_index": 0,
                  "decision": "pass",
                  "summary": "Matches the target software engineering role."
                }
              ]
            }
            """
        ),
    )

    assert result.items[0].decision == "pass"
    assert result.items[1].decision == "pass"
    assert result.items[1].summary == "Title screening did not return a result for this title, so it will continue to deeper review."


def test_classify_job_titles_falls_back_to_pass_on_bad_output() -> None:
    result = classify_job_titles(
        "new grad software engineer",
        ["Unknown Role"],
        client=_FakeClient("not-json"),
    )

    assert result.source == "system_fallback"
    assert result.items[0].decision == "pass"
