from __future__ import annotations

from app.domains.accounts.service import ensure_account
from app.domains.questions.fingerprints import ApplyQuestion, fingerprint_question
from app.domains.questions.matching import resolve_questions
from app.domains.questions.models import AnswerEntry, QuestionAlias, QuestionTask, QuestionTemplate
from app.domains.jobs.models import Job


def _make_job(session, account_id: int, title: str = "Engineer") -> Job:
    job = Job(
        account_id=account_id,
        canonical_key=f"acme-{title.lower().replace(' ', '-')}",
        company_name="Acme",
        title=title,
        status="new",
    )
    session.add(job)
    session.flush()
    return job


def _ask(prompt: str, field_type: str = "input_text") -> ApplyQuestion:
    return ApplyQuestion(key="q", prompt_text=prompt, field_type=field_type, required=True)


def test_new_template_generates_suggestion_for_similar_prompt(db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")

    resolve_questions(db_session, account.id, [_ask("Last name")])
    db_session.commit()

    resolve_questions(db_session, account.id, [_ask("Family name")])
    db_session.commit()

    aliases = db_session.scalars(
        __import__("sqlalchemy", fromlist=["select"]).select(QuestionAlias).where(
            QuestionAlias.account_id == account.id,
            QuestionAlias.status == "suggested",
        )
    ).all()
    assert len(aliases) == 1
    assert aliases[0].similarity_score >= 0.6


def test_no_suggestion_for_dissimilar_prompts(db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")

    resolve_questions(db_session, account.id, [_ask("Last name")])
    db_session.commit()
    resolve_questions(db_session, account.id, [_ask("Preferred start date")])
    db_session.commit()

    from sqlalchemy import select
    aliases = db_session.scalars(
        select(QuestionAlias).where(
            QuestionAlias.account_id == account.id,
            QuestionAlias.status == "suggested",
        )
    ).all()
    assert len(aliases) == 0


def test_no_suggestion_for_different_field_type(db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")

    resolve_questions(db_session, account.id, [_ask("Name", "input_text")])
    db_session.commit()
    resolve_questions(db_session, account.id, [_ask("Name", "single_select")])
    db_session.commit()

    from sqlalchemy import select
    aliases = db_session.scalars(
        select(QuestionAlias).where(QuestionAlias.account_id == account.id)
    ).all()
    assert len(aliases) == 0


def test_approved_alias_routes_resolution_to_canonical_answer(db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")

    last_name_fp = fingerprint_question("Last name", "input_text", [])
    template = QuestionTemplate(
        account_id=account.id,
        fingerprint=last_name_fp,
        prompt_text="Last name",
        field_type="input_text",
        option_labels=[],
    )
    db_session.add(template)
    db_session.flush()

    answer = AnswerEntry(
        account_id=account.id,
        question_template_id=template.id,
        label="Last name",
        answer_text="Smith",
    )
    db_session.add(answer)

    family_name_fp = fingerprint_question("Family name", "input_text", [])
    alias = QuestionAlias(
        account_id=account.id,
        source_fingerprint=family_name_fp,
        canonical_fingerprint=last_name_fp,
        status="approved",
        similarity_score=0.8,
    )
    db_session.add(alias)
    db_session.commit()

    resolved = resolve_questions(db_session, account.id, [_ask("Family name")])

    assert resolved[0].answer_entry is not None
    assert resolved[0].answer_value == "Smith"


def test_rejected_alias_does_not_route_resolution(db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")

    last_name_fp = fingerprint_question("Last name", "input_text", [])
    template = QuestionTemplate(
        account_id=account.id,
        fingerprint=last_name_fp,
        prompt_text="Last name",
        field_type="input_text",
        option_labels=[],
    )
    db_session.add(template)
    db_session.flush()

    answer = AnswerEntry(
        account_id=account.id,
        question_template_id=template.id,
        label="Last name",
        answer_text="Smith",
    )
    db_session.add(answer)

    family_name_fp = fingerprint_question("Family name", "input_text", [])
    alias = QuestionAlias(
        account_id=account.id,
        source_fingerprint=family_name_fp,
        canonical_fingerprint=last_name_fp,
        status="rejected",
        similarity_score=0.8,
    )
    db_session.add(alias)
    db_session.commit()

    resolved = resolve_questions(db_session, account.id, [_ask("Family name")])

    assert resolved[0].answer_entry is None


def test_approve_alias_via_api_migrates_existing_tasks(auth_client, db_session) -> None:
    from sqlalchemy import select

    account = ensure_account(db_session, "owner@example.com")
    job = _make_job(db_session, account.id)

    last_name_fp = fingerprint_question("Last name", "input_text", [])
    family_name_fp = fingerprint_question("Family name", "input_text", [])

    canonical_template = QuestionTemplate(
        account_id=account.id,
        fingerprint=last_name_fp,
        prompt_text="Last name",
        field_type="input_text",
        option_labels=[],
    )
    source_template = QuestionTemplate(
        account_id=account.id,
        fingerprint=family_name_fp,
        prompt_text="Family name",
        field_type="input_text",
        option_labels=[],
    )
    db_session.add_all([canonical_template, source_template])
    db_session.flush()

    task = QuestionTask(
        account_id=account.id,
        job_id=job.id,
        question_template_id=source_template.id,
        question_fingerprint=family_name_fp,
        prompt_text="Family name",
        field_type="input_text",
        option_labels=[],
        status="new",
    )
    db_session.add(task)

    alias = QuestionAlias(
        account_id=account.id,
        source_fingerprint=family_name_fp,
        canonical_fingerprint=last_name_fp,
        status="suggested",
        similarity_score=0.8,
    )
    db_session.add(alias)
    db_session.commit()

    resp = auth_client.patch(f"/api/questions/aliases/{alias.id}", json={"status": "approved"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"

    db_session.expire_all()
    db_session.refresh(task)
    assert task.question_fingerprint == last_name_fp
    assert task.question_template_id == canonical_template.id


def test_approve_alias_blocked_when_chain_would_form(auth_client, db_session) -> None:
    from sqlalchemy import select

    account = ensure_account(db_session, "owner@example.com")

    fp_a = fingerprint_question("A question", "input_text", [])
    fp_b = fingerprint_question("B question", "input_text", [])
    fp_c = fingerprint_question("C question", "input_text", [])

    existing_approved = QuestionAlias(
        account_id=account.id,
        source_fingerprint=fp_a,
        canonical_fingerprint=fp_b,
        status="approved",
        similarity_score=0.9,
    )
    new_alias = QuestionAlias(
        account_id=account.id,
        source_fingerprint=fp_b,
        canonical_fingerprint=fp_c,
        status="suggested",
        similarity_score=0.85,
    )
    db_session.add_all([existing_approved, new_alias])
    db_session.commit()

    resp = auth_client.patch(f"/api/questions/aliases/{new_alias.id}", json={"status": "approved"})
    assert resp.status_code == 422


def test_list_aliases_returns_suggested_by_default(auth_client, db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")

    alias = QuestionAlias(
        account_id=account.id,
        source_fingerprint="family name::input_text::",
        canonical_fingerprint="last name::input_text::",
        status="suggested",
        similarity_score=0.8,
    )
    db_session.add(alias)
    db_session.commit()

    resp = auth_client.get("/api/questions/aliases")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["status"] == "suggested"


def test_reject_alias_via_api(auth_client, db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")

    alias = QuestionAlias(
        account_id=account.id,
        source_fingerprint="family name::input_text::",
        canonical_fingerprint="last name::input_text::",
        status="suggested",
        similarity_score=0.8,
    )
    db_session.add(alias)
    db_session.commit()

    resp = auth_client.patch(f"/api/questions/aliases/{alias.id}", json={"status": "rejected"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"

    listed = auth_client.get("/api/questions/aliases")
    assert listed.json() == []
