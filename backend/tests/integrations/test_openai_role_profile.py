from app.config import Settings
from app.integrations.openai.role_profile import expand_role_profile_prompt


def test_role_profile_expansion_uses_openai_when_available(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.integrations.openai.role_profile._expand_with_ai",
        lambda client, model, prompt: {
            "generated_titles": ["Software Engineer I", "Backend Engineer"],
            "generated_keywords": ["new grad", "distributed systems"],
        },
    )

    result = expand_role_profile_prompt(
        "new grad backend software engineer",
        settings=Settings(
            openai_api_key="test-key",
            openai_role_profile_model="gpt-5-mini",
        ),
        client=object(),
    )

    assert result["generated_titles"] == ["Backend Engineer", "Software Engineer I"]
    assert result["generated_keywords"] == []


def test_role_profile_expansion_falls_back_without_openai_configuration() -> None:
    result = expand_role_profile_prompt(
        "software engineer 1 / new grad",
        settings=Settings(openai_api_key=None, groq_api_key=None),
        client=None,
    )

    assert "Software Engineer 1 / New Grad" in result["generated_titles"]
    assert "New Grad, Software Engineer 1" in result["generated_titles"]
    assert result["generated_keywords"] == []


def test_role_profile_expansion_prefers_groq_configuration(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.integrations.openai.role_profile._expand_with_ai",
        lambda client, model, prompt: {
            "generated_titles": ["Associate Engineer"],
            "generated_keywords": ["entry level"],
        },
    )

    result = expand_role_profile_prompt(
        "early career software engineer",
        settings=Settings(
            groq_api_key="groq-test-key",
            groq_model="llama-3.3-70b-versatile",
            openai_api_key="openai-test-key",
            openai_role_profile_model="gpt-5-mini",
        ),
        client=object(),
    )

    assert result["generated_titles"] == ["Associate Engineer"]
    assert result["generated_keywords"] == []
