from __future__ import annotations

from dataclasses import dataclass, field
import re


@dataclass(slots=True)
class ApplyQuestion:
    key: str
    prompt_text: str
    field_type: str
    required: bool
    option_labels: list[str] = field(default_factory=list)
    placeholder_text: str | None = None


def normalize_question_text(value: str) -> str:
    collapsed = re.sub(r"\s+", " ", value.strip().lower())
    return collapsed


def fingerprint_question(
    prompt_text: str,
    field_type: str,
    option_labels: list[str] | None = None,
) -> str:
    normalized_prompt = normalize_question_text(prompt_text)
    normalized_type = normalize_question_text(field_type)
    normalized_options = sorted(
        normalize_question_text(option)
        for option in (option_labels or [])
        if option.strip()
    )
    options_key = "|".join(normalized_options)
    return f"{normalized_prompt}::{normalized_type}::{options_key}"


def fingerprint_apply_question(question: ApplyQuestion) -> str:
    return fingerprint_question(
        prompt_text=question.prompt_text,
        field_type=question.field_type,
        option_labels=question.option_labels,
    )
