from __future__ import annotations

from app.domains.accounts.service import ensure_account
from app.domains.questions.fingerprints import ApplyQuestion, fingerprint_question
from app.domains.questions.matching import resolve_questions
from app.domains.questions.models import AnswerEntry, QuestionTemplate


def _make_template(session, account_id: int, options: list[str]) -> QuestionTemplate:
    fp = fingerprint_question("Preferred location", "single_select", options)
    template = QuestionTemplate(
        account_id=account_id,
        fingerprint=fp,
        prompt_text="Preferred location",
        field_type="single_select",
        option_labels=options,
    )
    session.add(template)
    session.flush()
    return template


def _make_ranked_answer(session, account_id: int, template: QuestionTemplate, ranked: list[str]) -> AnswerEntry:
    answer = AnswerEntry(
        account_id=account_id,
        question_template_id=template.id,
        label="Location preference",
        answer_payload={"ranked_options": ranked},
    )
    session.add(answer)
    session.flush()
    return answer


def _ask(account_id: int, options: list[str]) -> ApplyQuestion:
    return ApplyQuestion(
        key="preferred_location",
        prompt_text="Preferred location",
        field_type="single_select",
        required=True,
        option_labels=options,
    )


def test_ranked_first_match_returned(db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    template = _make_template(db_session, account.id, ["SF", "NYC"])
    _make_ranked_answer(db_session, account.id, template, ["SF", "NYC"])
    db_session.commit()

    resolved = resolve_questions(db_session, account.id, [_ask(account.id, ["SF", "NYC"])])

    assert resolved[0].answer_value == "SF"


def test_ranked_skips_absent_options_to_find_match(db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    template = _make_template(db_session, account.id, ["Tampa", "Houston", "SF"])
    _make_ranked_answer(db_session, account.id, template, ["SF", "Tampa"])
    db_session.commit()

    resolved = resolve_questions(db_session, account.id, [_ask(account.id, ["Tampa", "Houston", "SF"])])

    assert resolved[0].answer_value == "SF"


def test_ranked_falls_back_to_lower_rank_when_first_absent(db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    template = _make_template(db_session, account.id, ["Tampa", "Houston"])
    _make_ranked_answer(db_session, account.id, template, ["SF", "Tampa"])
    db_session.commit()

    resolved = resolve_questions(db_session, account.id, [_ask(account.id, ["Tampa", "Houston"])])

    assert resolved[0].answer_value == "Tampa"


def test_ranked_no_match_returns_none_answer(db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    template = _make_template(db_session, account.id, ["Boston", "Chicago"])
    _make_ranked_answer(db_session, account.id, template, ["SF", "Tampa"])
    db_session.commit()

    resolved = resolve_questions(db_session, account.id, [_ask(account.id, ["Boston", "Chicago"])])

    assert resolved[0].answer_entry is None
    assert resolved[0].answer_value is None


def test_ranked_empty_list_returns_none_answer(db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    template = _make_template(db_session, account.id, ["SF", "NYC"])
    _make_ranked_answer(db_session, account.id, template, [])
    db_session.commit()

    resolved = resolve_questions(db_session, account.id, [_ask(account.id, ["SF", "NYC"])])

    assert resolved[0].answer_entry is None


def test_ranked_comparison_is_case_insensitive(db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    fp = fingerprint_question("Preferred location", "single_select", ["SF", "NYC"])
    template = QuestionTemplate(
        account_id=account.id,
        fingerprint=fp,
        prompt_text="Preferred location",
        field_type="single_select",
        option_labels=["SF", "NYC"],
    )
    db_session.add(template)
    db_session.flush()
    _make_ranked_answer(db_session, account.id, template, ["sf", "nyc"])
    db_session.commit()

    resolved = resolve_questions(db_session, account.id, [_ask(account.id, ["SF", "NYC"])])

    assert resolved[0].answer_value == "SF"


def test_plain_value_answer_still_works(db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    template = _make_template(db_session, account.id, ["SF", "NYC"])
    answer = AnswerEntry(
        account_id=account.id,
        question_template_id=template.id,
        label="Location",
        answer_payload={"value": "SF"},
    )
    db_session.add(answer)
    db_session.commit()

    resolved = resolve_questions(db_session, account.id, [_ask(account.id, ["SF", "NYC"])])

    assert resolved[0].answer_value == "SF"


def test_ranked_answer_value_is_string_not_dict(db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    template = _make_template(db_session, account.id, ["SF", "NYC"])
    _make_ranked_answer(db_session, account.id, template, ["SF", "Tampa"])
    db_session.commit()

    resolved = resolve_questions(db_session, account.id, [_ask(account.id, ["SF", "NYC"])])

    value = resolved[0].answer_value
    assert isinstance(value, str), f"Expected str, got {type(value)}: {value}"


def test_ranked_answer_returns_canonical_casing_from_job_options(db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    fp = fingerprint_question("Preferred location", "single_select", ["SF", "NYC"])
    template = QuestionTemplate(
        account_id=account.id,
        fingerprint=fp,
        prompt_text="Preferred location",
        field_type="single_select",
        option_labels=["SF", "NYC"],
    )
    db_session.add(template)
    db_session.flush()
    _make_ranked_answer(db_session, account.id, template, ["sf"])
    db_session.commit()

    resolved = resolve_questions(db_session, account.id, [_ask(account.id, ["SF", "NYC"])])

    assert resolved[0].answer_value == "SF"
