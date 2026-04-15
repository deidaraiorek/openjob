from __future__ import annotations

import html as html_lib
import json
import re
from typing import Any

import httpx

from app.domains.questions.fingerprints import ApplyQuestion

_OPTIONAL_URL_NAMES = {"urls[LinkedIn]", "urls[Twitter]", "urls[GitHub]", "urls[Portfolio]", "urls[Other]"}
_EEO_NAMES = {"eeo[gender]", "eeo[race]", "eeo[veteran]"}

_FIELD_TYPE_MAP = {
    "multiple-choice": "radio",
    "multiple-select": "checkbox",
    "textarea": "textarea",
    "text": "text",
    "file": "file",
    "email": "email",
    "tel": "tel",
}


def fetch_question_payload(posting_id: str, company_slug: str | None = None) -> dict[str, Any]:
    apply_url = (
        f"https://jobs.lever.co/{company_slug}/{posting_id}/apply"
        if company_slug
        else f"https://jobs.lever.co/{posting_id}/apply"
    )
    response = httpx.get(apply_url, timeout=30.0, follow_redirects=True, headers={
        "User-Agent": "Mozilla/5.0 (compatible; OpenJob/1.0)",
    })
    response.raise_for_status()
    return {"html": response.text, "url": apply_url}


def parse_question_payload(payload: dict[str, Any]) -> list[ApplyQuestion]:
    html = payload["html"]
    questions: list[ApplyQuestion] = []

    form_m = re.search(r'<form[^>]*id="application-form"[^>]*>(.*?)</form>', html, re.DOTALL)
    if not form_m:
        return questions
    form_html = form_m.group(1)

    # Strip out the custom-cards section before parsing standard fields so we don't double-count
    form_html_no_cards = re.sub(
        r'<div[^>]*data-qa="additional-cards"[^>]*>.*?</div>\s*</div>', '', form_html, flags=re.DOTALL
    )

    # --- Standard personal info fields (resume, name, email, phone, location, org) ---
    standard_li = re.findall(
        r'<li[^>]*class="[^"]*application-question[^"]*"[^>]*>(.*?)</li>', form_html_no_cards, re.DOTALL
    )
    for li_html in standard_li:
        input_m = re.search(r'<input[^>]+name="([^"]+)"[^>]+type="([^"]+)"', li_html) or \
                  re.search(r'<input[^>]+type="([^"]+)"[^>]+name="([^"]+)"', li_html)
        if not input_m:
            continue
        # Normalise regardless of attribute order
        groups = input_m.groups()
        if groups[0] in ("text", "email", "tel", "file", "radio", "checkbox", "hidden", "submit"):
            field_type, name = groups[0], groups[1]
        else:
            name, field_type = groups[0], groups[1]

        if field_type in ("hidden", "submit") or name in _EEO_NAMES or name.startswith("cards["):
            continue

        label_m = re.search(r'<div[^>]*class="[^"]*application-label[^"]*"[^>]*>(.*?)</div>', li_html, re.DOTALL)
        label_text = re.sub(r'<[^>]+>', '', label_m.group(1)).strip().replace('\u2731', '').replace('✱', '').strip() if label_m else name
        required = ('✱' in li_html or '\u2731' in li_html) and name not in _OPTIONAL_URL_NAMES

        questions.append(ApplyQuestion(
            key=name,
            prompt_text=label_text,
            field_type=field_type,
            required=required,
            option_labels=[],
        ))

    # --- Custom question cards (JSON embedded in hidden input) ---
    cards_block_m = re.search(r'data-qa="additional-cards"[^>]*>(.*?)</div>\s*</div>', form_html, re.DOTALL)
    if cards_block_m:
        cards_html = cards_block_m.group(1)
        hidden_vals = re.findall(r'<input[^>]+type="hidden"[^>]+value="([^"]*)"', cards_html)
        for raw_val in hidden_vals:
            try:
                data = json.loads(html_lib.unescape(raw_val))
            except Exception:
                continue
            if "fields" not in data:
                continue
            card_name = data.get("text", "")
            for i, field in enumerate(data["fields"]):
                field_type = _FIELD_TYPE_MAP.get(field.get("type", "text"), "text")
                text = field.get("text") or field.get("description") or f"{card_name} field {i}"
                options = [o.get("text", "") for o in field.get("options") or [] if o.get("text")]
                required = bool(field.get("required"))
                card_id = data.get("id", "card")
                questions.append(ApplyQuestion(
                    key=f"cards[{card_id}][field{i}]",
                    prompt_text=text,
                    field_type=field_type,
                    required=required,
                    option_labels=options,
                ))

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
    submission_payload: dict[str, Any],
    company_slug: str | None = None,
) -> dict[str, Any]:
    apply_url = (
        f"https://jobs.lever.co/{company_slug}/{posting_id}/apply"
        if company_slug
        else f"https://jobs.lever.co/{posting_id}/apply"
    )
    response = httpx.post(apply_url, json=submission_payload, timeout=30.0)
    response.raise_for_status()
    return response.json() if response.content else {"status": "submitted"}
