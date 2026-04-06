from app.domains.accounts.service import ensure_account
from app.domains.questions.fingerprints import ApplyQuestion, fingerprint_question
from app.domains.questions.matching import resolve_questions
from app.domains.questions.models import AnswerEntry, QuestionTemplate


def test_exact_fingerprint_match_reuses_saved_answer(db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    template = QuestionTemplate(
        account_id=account.id,
        fingerprint=fingerprint_question(
            "Are you authorized to work in the US?",
            "radio",
            ["Yes", "No"],
        ),
        prompt_text="Are you authorized to work in the US?",
        field_type="radio",
        option_labels=["Yes", "No"],
    )
    db_session.add(template)
    db_session.commit()
    db_session.refresh(template)

    answer = AnswerEntry(
        account_id=account.id,
        question_template_id=template.id,
        label="Work authorization",
        answer_text="Yes",
    )
    db_session.add(answer)
    db_session.commit()

    resolved = resolve_questions(
        db_session,
        account.id,
        [
            ApplyQuestion(
                key="work_authorization",
                prompt_text="Are you authorized to work in the US?",
                field_type="radio",
                required=True,
                option_labels=["Yes", "No"],
            )
        ],
    )

    assert len(resolved) == 1
    assert resolved[0].answer_entry is not None
    assert resolved[0].answer_entry.id == answer.id


def test_option_difference_does_not_reuse_saved_answer(db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    template = QuestionTemplate(
        account_id=account.id,
        fingerprint=fingerprint_question(
            "Are you authorized to work in the US?",
            "radio",
            ["Yes", "No"],
        ),
        prompt_text="Are you authorized to work in the US?",
        field_type="radio",
        option_labels=["Yes", "No"],
    )
    db_session.add(template)
    db_session.commit()
    db_session.refresh(template)

    answer = AnswerEntry(
        account_id=account.id,
        question_template_id=template.id,
        label="Work authorization",
        answer_text="Yes",
    )
    db_session.add(answer)
    db_session.commit()

    resolved = resolve_questions(
        db_session,
        account.id,
        [
            ApplyQuestion(
                key="work_authorization",
                prompt_text="Are you authorized to work in the US?",
                field_type="radio",
                required=True,
                option_labels=["Yes", "No", "Need sponsorship"],
            )
        ],
    )

    assert len(resolved) == 1
    assert resolved[0].answer_entry is None


def test_structured_answer_payload_unwraps_to_field_value(db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    template = QuestionTemplate(
        account_id=account.id,
        fingerprint=fingerprint_question(
            "How did you hear about us?",
            "multi_value_multi_select",
            ["LinkedIn", "Referral", "School"],
        ),
        prompt_text="How did you hear about us?",
        field_type="multi_value_multi_select",
        option_labels=["LinkedIn", "Referral", "School"],
    )
    db_session.add(template)
    db_session.commit()
    db_session.refresh(template)

    answer = AnswerEntry(
        account_id=account.id,
        question_template_id=template.id,
        label="Discovery sources",
        answer_text="LinkedIn, School",
        answer_payload={"values": ["LinkedIn", "School"]},
    )
    db_session.add(answer)
    db_session.commit()

    resolved = resolve_questions(
        db_session,
        account.id,
        [
            ApplyQuestion(
                key="discovery_source",
                prompt_text="How did you hear about us?",
                field_type="multi_value_multi_select",
                required=True,
                option_labels=["LinkedIn", "Referral", "School"],
            )
        ],
    )

    assert resolved[0].answer_entry is not None
    assert resolved[0].answer_value == ["LinkedIn", "School"]
