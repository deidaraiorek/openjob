import pytest
import app.integrations.openai.job_title_screening as job_title_screening
from app.config import Settings
from app.integrations.openai.job_title_screening import (
    JobTitleScreeningItem,
    JobTitleScreeningResult,
    classify_job_titles,
)


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
        settings=Settings(groq_api_key="test-key"),
        client=_FakeClient(
            """
            {
              "results": [
                {
                  "title_index": 0,
                  "decision": "pass",
                  "summary": "Matches the target software engineering role.",
                  "decision_rationale_type": "family_match",
                  "role_family_alignment": "same_family",
                  "seniority_alignment": "compatible",
                  "modifier_impact": "specialization_only",
                  "contradiction_strength": "none"
                },
                {
                  "title_index": 1,
                  "decision": "reject",
                  "summary": "Outside the target role family.",
                  "decision_rationale_type": "clear_family_mismatch",
                  "role_family_alignment": "different_family",
                  "seniority_alignment": "uncertain",
                  "modifier_impact": "material_scope_change",
                  "contradiction_strength": "strong"
                }
              ]
            }
            """
        ),
    )

    assert result.source == "ai"
    assert [item.decision for item in result.items] == ["pass", "reject"]
    assert result.items[0].payload["role_family_alignment"] == "same_family"
    assert result.items[1].payload["contradiction_strength"] == "strong"


def test_classify_job_titles_marks_missing_index_as_pass() -> None:
    result = classify_job_titles(
        "new grad software engineer",
        ["Software Engineer - AI Platform", "Data Engineer"],
        settings=Settings(groq_api_key="test-key"),
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
    assert result.items[1].summary == "Title screening did not return a result for this title, so it is pending a retry."


def test_classify_job_titles_falls_back_to_pass_on_bad_output() -> None:
    result = classify_job_titles(
        "new grad software engineer",
        ["Unknown Role"],
        settings=Settings(groq_api_key="test-key"),
        client=_FakeClient("not-json"),
    )

    assert result.source == "system_fallback"
    assert result.items[0].decision == "pass"
    assert result.items[0].failure_cause == "provider_response_invalid"


def test_classify_job_titles_does_not_accept_malformed_rejects() -> None:
    result = classify_job_titles(
        "software engineer new grad",
        ["Backend Engineer - New Grad"],
        settings=Settings(groq_api_key="test-key"),
        client=_FakeClient(
            """
            {
              "results": [
                {
                  "title_index": 0,
                  "decision": "reject",
                  "summary": "Different role family.",
                  "decision_rationale_type": "role_family_mismatch",
                  "role_family_alignment": "weak_match",
                  "seniority_alignment": "compatible",
                  "modifier_impact": "neutral",
                  "contradiction_strength": "moderate"
                }
              ]
            }
            """
        ),
    )

    assert result.items[0].source == "system_fallback"
    assert result.items[0].decision == "pass"
    assert result.items[0].failure_cause == "provider_response_invalid"


@pytest.mark.parametrize("title", [
    "Backend Engineer – New Grad",
    "Entry Level Full-Stack Developer",
    "Junior Software Developer - London - Bournemouth",
    "Software Developer – New Graduate",
    "Associate Software Engineer (AI Agent Developer)",
    "Graduate Software Developer",
])
def test_in_family_swe_new_grad_titles_pass_when_ai_returns_pass(title: str) -> None:
    result = classify_job_titles(
        "SWE new grad",
        [title],
        settings=Settings(groq_api_key="test-key"),
        client=_FakeClient(
            f"""
            {{
              "results": [
                {{
                  "title_index": 0,
                  "decision": "pass",
                  "summary": "Title is in the software engineering family at entry-career level.",
                  "decision_rationale_type": "family_match",
                  "role_family_alignment": "same_family",
                  "seniority_alignment": "compatible",
                  "modifier_impact": "specialization_only",
                  "contradiction_strength": "none"
                }}
              ]
            }}
            """
        ),
    )

    assert result.items[0].decision == "pass", f"Expected pass for '{title}', got {result.items[0].decision}"
    assert result.items[0].source == "ai"
    assert result.items[0].failure_cause is None


def test_hardware_engineer_rejects_when_ai_returns_clear_family_mismatch() -> None:
    result = classify_job_titles(
        "SWE new grad",
        ["Hardware Engineer"],
        settings=Settings(groq_api_key="test-key"),
        client=_FakeClient(
            """
            {
              "results": [
                {
                  "title_index": 0,
                  "decision": "reject",
                  "summary": "Hardware engineering is a different discipline from software engineering.",
                  "decision_rationale_type": "clear_family_mismatch",
                  "role_family_alignment": "different_family",
                  "seniority_alignment": "uncertain",
                  "modifier_impact": "material_scope_change",
                  "contradiction_strength": "strong"
                }
              ]
            }
            """
        ),
    )

    assert result.items[0].decision == "reject"
    assert result.items[0].source == "ai"
    assert result.items[0].payload["role_family_alignment"] == "different_family"


def test_unsafe_reject_overridden_to_pass_without_third_ai_call() -> None:
    ai_calls: list[dict] = []

    class _TrackingCompletions:
        def create(self, **kwargs):
            ai_calls.append(kwargs)

            class _Message:
                content = """
                {
                  "results": [
                    {
                      "title_index": 0,
                      "decision": "reject",
                      "summary": "Ambiguous seniority signals.",
                      "decision_rationale_type": "clear_seniority_mismatch",
                      "role_family_alignment": "same_family",
                      "seniority_alignment": "incompatible",
                      "modifier_impact": "specialization_only",
                      "contradiction_strength": "moderate"
                    }
                  ]
                }
                """

            class _Choice:
                message = _Message()

            class _Response:
                choices = [_Choice()]

            return _Response()

    class _TrackingChat:
        completions = _TrackingCompletions()

    class _TrackingClient:
        chat = _TrackingChat()

    result = classify_job_titles(
        "SWE new grad",
        ["Junior Backend Developer"],
        settings=Settings(groq_api_key="test-key"),
        client=_TrackingClient(),
    )

    assert len(ai_calls) == 1, "Only one AI call should be made — no verify loop"
    assert result.items[0].decision == "pass"
    assert result.items[0].decision_rationale_type == "ambiguous_but_passed"


def test_phase1_system_prompt_includes_role_family_context_for_early_career() -> None:
    captured_kwargs: list[dict] = []

    class _CapturingCompletions:
        def create(self, **kwargs):
            captured_kwargs.append(kwargs)

            class _Message:
                content = """
                {
                  "results": [
                    {
                      "title_index": 0,
                      "decision": "pass",
                      "summary": "Match.",
                      "decision_rationale_type": "family_match",
                      "role_family_alignment": "same_family",
                      "seniority_alignment": "compatible",
                      "modifier_impact": "none",
                      "contradiction_strength": "none"
                    }
                  ]
                }
                """

            class _Choice:
                message = _Message()

            class _Response:
                choices = [_Choice()]

            return _Response()

    class _CapturingChat:
        completions = _CapturingCompletions()

    class _CapturingClient:
        chat = _CapturingChat()

    classify_job_titles(
        "SWE new grad",
        ["Software Engineer I"],
        settings=Settings(groq_api_key="test-key"),
        client=_CapturingClient(),
    )

    assert captured_kwargs, "AI should have been called"
    system_content = captured_kwargs[0]["messages"][0]["content"]
    assert "early-career" in system_content or "new grad" in system_content or "entry level" in system_content.lower()
    assert "swe new grad" in system_content.lower() or "swe" in system_content.lower()


def test_classify_job_titles_keeps_item_metadata_when_one_batch_falls_back(monkeypatch) -> None:
    calls = {"count": 0}

    def fake_classify_batch_with_ai(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return JobTitleScreeningResult(
                items=[
                    JobTitleScreeningItem(
                        title="Associate Software Engineer (AI Agent Developer)",
                        decision="reject",
                        summary="Title suggests a different role family.",
                        decision_rationale_type="clear_family_mismatch",
                        source="ai",
                        model_name="groq-test",
                        failure_cause=None,
                        payload={"role_family_alignment": "different_family"},
                    )
                ],
                source="ai",
                model_name="groq-test",
                failure_cause=None,
                payload={"batch": 1},
            )
        raise ValueError("bad output")

    monkeypatch.setattr(job_title_screening, "_classify_batch_with_ai", fake_classify_batch_with_ai)

    result = classify_job_titles(
        "new grad software engineer",
        ["Associate Software Engineer (AI Agent Developer)", "Data Engineer"],
        settings=Settings(groq_api_key="test-key", title_screening_batch_size=1),
        client=_FakeClient("{}"),
    )

    assert result.source == "system_fallback"
    assert result.items[0].source == "ai"
    assert result.items[0].failure_cause is None
    assert result.items[0].decision == "reject"
    assert result.items[1].source == "system_fallback"
    assert result.items[1].failure_cause == "provider_response_invalid"
