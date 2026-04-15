from __future__ import annotations

from typing import Any

import httpx

from app.domains.questions.fingerprints import ApplyQuestion


def fetch_question_payload(job_posting_id: str) -> dict[str, Any]:
    response = httpx.post(
        "https://api.ashbyhq.com/applicationForm.info",
        json={"jobPostingId": job_posting_id},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json().get("results", {})


def parse_question_payload(payload: dict[str, Any]) -> list[ApplyQuestion]:
    questions: list[ApplyQuestion] = []

    for field_group in payload.get("fieldGroups", []) or []:
        for field in field_group.get("fields", []) or []:
            field_def = field.get("field", {}) or {}
            field_type = field_def.get("type", "ShortText")
            field_key = field_def.get("id") or field_def.get("path") or field.get("descriptionPlain", "")
            label = field_def.get("title") or field.get("descriptionPlain") or field_key
            required = bool(field.get("isRequired"))

            if not field_key:
                continue

            select_options = field_def.get("selectableValues", []) or []
            option_labels = [opt.get("label", "") for opt in select_options if opt.get("label")]

            ashby_to_internal = {
                "ShortText": "input_text",
                "LongText": "textarea",
                "Boolean": "boolean",
                "Date": "date",
                "Email": "input_text",
                "Phone": "input_text",
                "Number": "input_text",
                "Dropdown": "multi_value_single_select",
                "MultiSelect": "multi_value_multi_select",
                "FileUpload": "input_file",
            }
            internal_type = ashby_to_internal.get(field_type, "input_text")

            questions.append(
                ApplyQuestion(
                    key=field_key,
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
    field_submissions: list[dict[str, Any]] = []

    for question in questions:
        if question.key not in answers_by_key:
            continue
        field_submissions.append({
            "path": question.key,
            "value": answers_by_key[question.key],
        })

    return {"fieldSubmissions": field_submissions}


def submit_application(
    job_posting_id: str,
    submission_payload: dict[str, Any],
) -> dict[str, Any]:
    response = httpx.post(
        "https://api.ashbyhq.com/applicationForm.submit",
        json={"jobPostingId": job_posting_id, **submission_payload},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json().get("results", {"status": "submitted"})
