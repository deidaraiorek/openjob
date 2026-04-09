from pathlib import Path

from app.config import get_settings
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


def test_upload_answer_file_persists_metadata(auth_client, tmp_path) -> None:
    settings = get_settings()
    original_storage_dir = settings.answer_file_storage_dir
    settings.answer_file_storage_dir = str(tmp_path)

    try:
        response = auth_client.post(
            "/api/answers/upload",
            data={"label": "Default Resume"},
            files={"upload": ("resume.pdf", b"resume-bytes", "application/pdf")},
        )
    finally:
        settings.answer_file_storage_dir = original_storage_dir

    assert response.status_code == 201
    payload = response.json()
    assert payload["label"] == "Default Resume"
    assert payload["answer_text"] is None
    assert payload["answer_payload"]["kind"] == "file"
    assert payload["answer_payload"]["filename"] == "resume.pdf"
    assert payload["answer_payload"]["mime_type"] == "application/pdf"
    assert payload["answer_payload"]["size_bytes"] == len(b"resume-bytes")
    assert Path(payload["answer_payload"]["stored_path"]).exists()
