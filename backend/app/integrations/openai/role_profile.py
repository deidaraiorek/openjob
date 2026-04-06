from __future__ import annotations

import json
from itertools import permutations
import re
from typing import Any

from openai import OpenAI

from app.config import Settings, get_settings


def _normalize_values(values: list[str]) -> list[str]:
    normalized = {
        " ".join(value.strip().split())
        for value in values
        if isinstance(value, str) and value.strip()
    }
    return sorted(normalized)


def _prompt_words(prompt: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", prompt.lower())


def _clean_prompt(prompt: str) -> str:
    cleaned = prompt.lower()
    cleaned = re.sub(r"\b(roles?|jobs?|positions?|opportunities?)\b", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _title_case_phrase(phrase: str) -> str:
    return " ".join(word.capitalize() if word not in {"i", "ii", "iii", "iv"} else word.upper() for word in phrase.split())


def _swap_level_markers(phrase: str) -> set[str]:
    variants = {phrase}
    replacements = {
        " i ": [" 1 "],
        " ii ": [" 2 "],
        " iii ": [" 3 "],
        " iv ": [" 4 "],
        " 1 ": [" i "],
        " 2 ": [" ii "],
        " 3 ": [" iii "],
        " 4 ": [" iv "],
    }
    padded = f" {phrase} "
    for source, targets in replacements.items():
        if source in padded:
            for target in targets:
                variants.add(padded.replace(source, target).strip())
    return variants


def _prompt_chunks(prompt: str) -> list[str]:
    cleaned = _clean_prompt(prompt)
    chunks = [
        " ".join(chunk.strip().split())
        for chunk in re.split(r"\s*(?:/|,|;|\||\band\b)\s*", cleaned)
        if chunk.strip()
    ]
    return chunks or ([cleaned] if cleaned else [])


def _fallback_expand_role_profile_prompt(prompt: str) -> dict[str, list[str]]:
    titles: set[str] = set()
    chunks = _prompt_chunks(prompt)

    if chunks:
        for ordered_chunks in permutations(chunks):
            for separator in (" ", ", ", " - "):
                phrase = separator.join(ordered_chunks).strip()
                if not phrase:
                    continue
                for variant in _swap_level_markers(phrase):
                    titles.add(_title_case_phrase(variant))

        cleaned_prompt = _clean_prompt(prompt)
        if cleaned_prompt:
            for variant in _swap_level_markers(cleaned_prompt):
                titles.add(_title_case_phrase(variant))

    return {
        "generated_titles": _normalize_values(list(titles)),
        "generated_keywords": [],
    }


def _build_ai_client(settings: Settings) -> tuple[OpenAI | None, str]:
    if settings.groq_api_key:
        return (
            OpenAI(api_key=settings.groq_api_key, base_url=settings.groq_base_url),
            settings.groq_model,
        )
    if not settings.openai_api_key:
        return None, settings.openai_role_profile_model
    return OpenAI(api_key=settings.openai_api_key), settings.openai_role_profile_model


def _extract_completion_text(response: Any) -> str:
    content = response.choices[0].message.content
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        fragments: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("text"):
                fragments.append(item["text"])
        return "".join(fragments)

    return str(content)


def _expand_with_ai(client: OpenAI, model: str, prompt: str) -> dict[str, list[str]]:
    response = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "Expand a job-seeker role profile into an extensive but focused title catalog. "
                    "Return only job titles, not skills or keywords. "
                    "Include ordering variants, punctuation variants, and common level synonyms when they still fit the same target role. "
                    "Avoid unrelated specialties, senior titles, management titles, or adjacent tracks unless the prompt explicitly asks for them. "
                    "Respond as a JSON object with keys generated_titles and generated_keywords. "
                    "generated_keywords should always be an empty array."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Prompt: "
                    f"{prompt}\n"
                    "Return 18-40 title variants that maximize real-world title coverage for this role profile while staying in-family and in-seniority."
                ),
            },
        ],
    )

    payload = json.loads(_extract_completion_text(response))
    return {
        "generated_titles": _normalize_values(list(payload.get("generated_titles", []))),
        "generated_keywords": [],
    }


def expand_role_profile_prompt(
    prompt: str,
    *,
    settings: Settings | None = None,
    client: OpenAI | None = None,
) -> dict[str, list[str]]:
    resolved_settings = settings or get_settings()
    configured_client, configured_model = _build_ai_client(resolved_settings)
    resolved_client = client or configured_client

    if resolved_client is not None:
        try:
            expansion = _expand_with_ai(
                resolved_client,
                configured_model,
                prompt,
            )
            expansion = {
                "generated_titles": _normalize_values(expansion.get("generated_titles", [])),
                "generated_keywords": [],
            }
            if expansion["generated_titles"]:
                return expansion
        except Exception:
            pass

    return _fallback_expand_role_profile_prompt(prompt)
