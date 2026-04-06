from __future__ import annotations

from typing import Any

import httpx

from app.domains.questions.fingerprints import ApplyQuestion


def fetch_question_payload(posting_id: str) -> dict[str, Any]:
    response = httpx.get(
        f"https://api.lever.co/v0/postings/{posting_id}/apply",
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def parse_question_payload(payload: dict[str, Any]) -> list[ApplyQuestion]:
    questions: list[ApplyQuestion] = []

    for field in payload.get("personalInformation", []) or []:
        questions.append(
            ApplyQuestion(
                key=field["name"],
                prompt_text=field.get("text", field["name"]),
                field_type=field.get("type", "text"),
                required=bool(field.get("required")),
                option_labels=[option.get("text", "") for option in field.get("options", []) or [] if option.get("text")],
            ),
        )

    for custom_question in payload.get("customQuestions", []) or []:
        for field in custom_question.get("fields", []) or []:
            questions.append(
                ApplyQuestion(
                    key=field["name"],
                    prompt_text=field.get("text", custom_question.get("text", field["name"])),
                    field_type=field.get("type", "text"),
                    required=bool(field.get("required", custom_question.get("required"))),
                    option_labels=[option.get("text", "") for option in field.get("options", []) or [] if option.get("text")],
                ),
            )

    for field in payload.get("urls", []) or []:
        questions.append(
            ApplyQuestion(
                key=field["name"],
                prompt_text=field.get("text", field["name"]),
                field_type=field.get("type", "text"),
                required=bool(field.get("required")),
                option_labels=[],
            ),
        )

    return questions


def build_submission_payload(
    questions: list[ApplyQuestion],
    answers_by_key: dict[str, Any],
) -> dict[str, Any]:
    fields = []
    for question in questions:
        if question.key not in answers_by_key:
            continue
        fields.append({"name": question.key, "value": answers_by_key[question.key]})
    return {"fields": fields}


def submit_application(
    posting_id: str,
    api_key: str,
    submission_payload: dict[str, Any],
) -> dict[str, Any]:
    response = httpx.post(
        f"https://api.lever.co/v0/postings/{posting_id}",
        auth=(api_key, ""),
        json=submission_payload,
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json() if response.content else {"status": "submitted"}
