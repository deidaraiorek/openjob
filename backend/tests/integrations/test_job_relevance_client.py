from app.domains.accounts.service import ensure_account
from app.domains.role_profiles.models import RoleProfile
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
        client=_FakeClient(
            """
            {
              "decision": "match",
              "score": 0.91,
              "summary": "The role is clearly early-career backend software work.",
              "matched_signals": ["backend", "university graduate"],
              "concerns": []
            }
            """
        ),
    )

    assert result.decision == "match"
    assert result.score == 0.91
    assert result.matched_signals == ["backend", "university graduate"]


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
        client=_FakeClient("not-json"),
    )

    assert result.decision == "review"
    assert result.source == "system_fallback"
