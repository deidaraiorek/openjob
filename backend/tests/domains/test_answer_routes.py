from app.domains.accounts.service import ensure_account
from app.domains.questions.models import AnswerEntry


def test_update_answer_entry_persists_changes(auth_client, db_session) -> None:
    account = ensure_account(db_session, "owner@example.com")
    answer = AnswerEntry(
        account_id=account.id,
        label="First Name",
        answer_text="Dang",
        answer_payload={},
    )
    db_session.add(answer)
    db_session.commit()
    db_session.refresh(answer)

    response = auth_client.put(
        f"/api/answers/{answer.id}",
        json={
            "question_template_id": None,
            "label": "Preferred First Name",
            "answer_text": "Huu Dang",
            "answer_payload": {},
        },
    )

    assert response.status_code == 200
    assert response.json()["label"] == "Preferred First Name"
    assert response.json()["answer_text"] == "Huu Dang"
