from __future__ import annotations

from typing import Any

import httpx

from app.domains.questions.fingerprints import ApplyQuestion


def fetch_question_payload(board_token: str, job_post_id: str) -> dict[str, Any]:
    response = httpx.get(
        f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs/{job_post_id}",
        params={"questions": "true"},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def parse_question_payload(payload: dict[str, Any]) -> list[ApplyQuestion]:
    questions: list[ApplyQuestion] = []

    for collection_key in ("questions", "location_questions", "compliance"):
        for entry in payload.get(collection_key, []) or []:
            fields = entry.get("fields") or []
            visible_field = next(
                (field for field in fields if field.get("type") != "input_hidden"),
                None,
            )
            if not visible_field:
                continue

            option_labels = [
                option.get("label", "")
                for option in visible_field.get("values", []) or []
                if option.get("label")
            ]
            questions.append(
                ApplyQuestion(
                    key=visible_field.get("name") or entry.get("label", ""),
                    prompt_text=entry.get("label") or visible_field.get("name", "Unnamed field"),
                    field_type=visible_field.get("type", "input_text"),
                    required=bool(entry.get("required")),
                    option_labels=option_labels,
                ),
            )

    return questions


def build_submission_payload(
    questions: list[ApplyQuestion],
    answers_by_key: dict[str, Any],
) -> dict[str, Any]:
    payload: dict[str, Any] = {}

    for question in questions:
        if question.key not in answers_by_key:
            continue
        payload[question.key] = answers_by_key[question.key]

    return payload


def submit_application(
    board_token: str,
    job_post_id: str,
    api_key: str,
    submission_payload: dict[str, Any],
) -> dict[str, Any]:
    response = httpx.post(
        f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs/{job_post_id}",
        auth=httpx.BasicAuth(api_key, ""),
        json=submission_payload,
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json() if response.content else {"status": "submitted"}
