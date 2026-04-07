from app.domains.accounts.service import ensure_account
from app.domains.role_profiles.models import RoleProfile
from app.config import Settings
from app.integrations.openai.job_relevance import classify_job_relevance


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


def test_classify_job_relevance_parses_structured_json(db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    profile = RoleProfile(
        account_id=account.id,
        prompt="new grad backend software engineer",
        generated_titles=["Software Engineer I"],
        generated_keywords=[],
    )

    result = classify_job_relevance(
        profile,
        title="Backend Engineer, University Graduate",
        company_name="Acme",
        location="Remote",
        source_type="greenhouse_board",
        apply_target_type="greenhouse_apply",
        settings=Settings(groq_api_key="test-key"),
        client=_FakeClient(
            """
            {
              "results": [
                {
                  "job_index": 0,
                  "decision": "match",
                  "score": 0.91,
                  "summary": "The role is clearly early-career backend software work.",
                  "decision_rationale_type": "family_match",
                  "role_family_alignment": "same_family",
                  "seniority_alignment": "adjacent_or_same",
                  "modifier_impact": "specialization_only",
                  "contradiction_strength": "none",
                  "matched_signals": ["backend", "university graduate"],
                  "concerns": []
                }
              ]
            }
            """
        ),
    )

    assert result.decision == "match"
    assert result.score == 0.91
    assert result.matched_signals == ["backend", "university graduate"]
    assert result.payload["role_family_alignment"] == "same_family"
    assert result.payload["seniority_alignment"] == "adjacent_or_same"


def test_classify_job_relevance_returns_match_for_in_family_swe_role(db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    profile = RoleProfile(
        account_id=account.id,
        prompt="SWE new grad",
        generated_titles=["Software Engineer I", "Junior Software Engineer", "Graduate Software Engineer"],
        generated_keywords=[],
    )

    result = classify_job_relevance(
        profile,
        title="Junior Software Developer - London",
        company_name="Acme",
        location="London",
        source_type="greenhouse_board",
        apply_target_type="greenhouse_apply",
        title_screening_decision="pass",
        title_screening_summary="In-family SWE title at entry-career level.",
        title_screening_source="ai",
        settings=Settings(groq_api_key="test-key"),
        client=_FakeClient(
            """
            {
              "results": [
                {
                  "job_index": 0,
                  "decision": "match",
                  "score": 0.93,
                  "summary": "Junior software developer is an in-family early-career SWE role.",
                  "decision_rationale_type": "family_match",
                  "role_family_alignment": "same_family",
                  "seniority_alignment": "adjacent_or_same",
                  "modifier_impact": "specialization_only",
                  "contradiction_strength": "none",
                  "matched_signals": ["junior software developer", "new grad"],
                  "concerns": []
                }
              ]
            }
            """
        ),
    )

    assert result.decision == "match"
    assert result.source == "ai"
    assert result.score == 0.93


def test_classify_job_relevance_repair_inconsistency_falls_to_review_not_exception(db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    profile = RoleProfile(
        account_id=account.id,
        prompt="SWE new grad",
        generated_titles=["Software Engineer I"],
        generated_keywords=[],
    )

    call_count = {"n": 0}

    class _AlwaysInconsistentCompletions:
        def create(self, **kwargs):
            call_count["n"] += 1

            class _Message:
                content = """
                {
                  "results": [
                    {
                      "job_index": 0,
                      "decision": "match",
                      "score": 0.5,
                      "summary": "Inconsistent result.",
                      "decision_rationale_type": "clear_family_mismatch",
                      "role_family_alignment": "different_family",
                      "seniority_alignment": "uncertain",
                      "modifier_impact": "material_scope_change",
                      "contradiction_strength": "strong",
                      "matched_signals": [],
                      "concerns": []
                    }
                  ]
                }
                """

            class _Choice:
                message = _Message()

            class _Response:
                choices = [_Choice()]

            return _Response()

    class _AlwaysInconsistentChat:
        completions = _AlwaysInconsistentCompletions()

    class _AlwaysInconsistentClient:
        chat = _AlwaysInconsistentChat()

    result = classify_job_relevance(
        profile,
        title="Some Role",
        settings=Settings(groq_api_key="test-key"),
        client=_AlwaysInconsistentClient(),
    )

    assert result.decision == "review"
    assert result.source in {"ai", "system_fallback"}


def test_classify_job_relevance_uses_json_schema_format(db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    profile = RoleProfile(
        account_id=account.id,
        prompt="SWE new grad",
        generated_titles=["Software Engineer I"],
        generated_keywords=[],
    )

    captured_kwargs: list[dict] = []

    class _CapturingCompletions:
        def create(self, **kwargs):
            captured_kwargs.append(kwargs)

            class _Message:
                content = """
                {
                  "results": [
                    {
                      "job_index": 0,
                      "decision": "match",
                      "score": 0.9,
                      "summary": "Match.",
                      "decision_rationale_type": "family_match",
                      "role_family_alignment": "same_family",
                      "seniority_alignment": "adjacent_or_same",
                      "modifier_impact": "none",
                      "contradiction_strength": "none",
                      "matched_signals": [],
                      "concerns": []
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

    classify_job_relevance(
        profile,
        title="Software Engineer I",
        settings=Settings(groq_api_key="test-key"),
        client=_CapturingClient(),
    )

    assert captured_kwargs, "AI should have been called"
    response_format = captured_kwargs[0].get("response_format", {})
    assert response_format.get("type") == "json_schema", f"Expected json_schema format, got: {response_format}"


def test_classify_job_relevance_falls_back_to_review_on_bad_output(db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    profile = RoleProfile(
        account_id=account.id,
        prompt="new grad backend software engineer",
        generated_titles=["Software Engineer I"],
        generated_keywords=[],
    )

    result = classify_job_relevance(
        profile,
        title="Unknown Role",
        settings=Settings(groq_api_key="test-key"),
        client=_FakeClient("not-json"),
    )

    assert result.decision == "review"
    assert result.source == "system_fallback"
