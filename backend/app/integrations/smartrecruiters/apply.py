from __future__ import annotations

from typing import Any

import httpx

from app.domains.questions.fingerprints import ApplyQuestion


def fetch_question_payload(posting_id: str) -> dict[str, Any]:
    response = httpx.get(
        f"https://api.smartrecruiters.com/v1/postings/{posting_id}/configuration/application-form",
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def parse_question_payload(payload: dict[str, Any]) -> list[ApplyQuestion]:
    questions: list[ApplyQuestion] = []

    sections = payload.get("sections", []) or []
    for section in sections:
        for field in section.get("fields", []) or []:
            field_id = field.get("id") or field.get("label", "")
            label = field.get("label") or field_id
            required = bool(field.get("required"))
            field_type = field.get("type", "TEXT")

            if not field_id:
                continue

            options = field.get("values", []) or []
            option_labels = [opt.get("label", "") for opt in options if opt.get("label")]

            sr_to_internal = {
                "TEXT": "input_text",
                "TEXTAREA": "textarea",
                "BOOLEAN": "boolean",
                "DATE": "date",
                "SINGLE_SELECT": "multi_value_single_select",
                "MULTI_SELECT": "multi_value_multi_select",
                "FILE": "input_file",
            }
            internal_type = sr_to_internal.get(field_type, "input_text")

            questions.append(
                ApplyQuestion(
                    key=field_id,
                    prompt_text=label,
                    field_type=internal_type,
                    required=required,
                    option_labels=option_labels,
                )
            )

    return questions


def build_submission_payload(
    questions: list[ApplyQuestion],
    answers_by_key: dict[str, Any],
) -> dict[str, Any]:
    answers: list[dict[str, Any]] = []

    for question in questions:
        if question.key not in answers_by_key:
            continue
        answers.append({
            "id": question.key,
            "value": answers_by_key[question.key],
        })

    return {"answers": answers}


def submit_application(
    posting_id: str,
    submission_payload: dict[str, Any],
) -> dict[str, Any]:
    response = httpx.post(
        f"https://api.smartrecruiters.com/v1/postings/{posting_id}/candidates",
        json=submission_payload,
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json() if response.content else {"status": "submitted"}
