from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Any


class DOMFillError(Exception):
    def __init__(self, message: str, missing_fields: list[str] | None = None):
        super().__init__(message)
        self.missing_fields = missing_fields or []


@dataclass
class FilledField:
    label: str
    field_type: str
    required: bool
    options: list[str] = field(default_factory=list)
    placeholder: str | None = None


@dataclass
class FillResult:
    submitted: bool
    missing_fields: list[FilledField] = field(default_factory=list)


_NEXT_BUTTON_TEXTS = {
    "next", "next step", "continue", "next page", "save and continue",
    "save & continue", "proceed",
}

_SUBMIT_BUTTON_TEXTS = {
    "submit", "submit application", "apply", "apply now", "send application",
    "complete application", "finish",
}

_SKIP_INPUT_TYPES = {"hidden", "submit", "reset", "button", "image", "file"}

_LABEL_SIMILARITY_THRESHOLD = 0.6


def _best_answer(label: str, answers: dict[str, Any]) -> Any | None:
    label_lower = label.lower().strip()

    for key, val in answers.items():
        if key.lower().strip() == label_lower:
            return val

    best_score = 0.0
    best_val = None
    for key, val in answers.items():
        score = difflib.SequenceMatcher(None, label_lower, key.lower().strip()).ratio()
        if score > best_score:
            best_score = score
            best_val = val

    if best_score >= _LABEL_SIMILARITY_THRESHOLD:
        return best_val
    return None


def _get_label_for_element(page: Any, element: Any) -> str:
    try:
        el_id = element.get_attribute("id")
        if el_id:
            label_el = page.locator(f'label[for="{el_id}"]')
            if label_el.count() > 0:
                text = label_el.first.inner_text().strip()
                if text:
                    return text

        aria_label = element.get_attribute("aria-label") or ""
        if aria_label.strip():
            return aria_label.strip()

        aria_labelledby = element.get_attribute("aria-labelledby") or ""
        if aria_labelledby.strip():
            for ref_id in aria_labelledby.split():
                ref = page.locator(f"#{ref_id}")
                if ref.count() > 0:
                    text = ref.first.inner_text().strip()
                    if text:
                        return text

        placeholder = element.get_attribute("placeholder") or ""
        if placeholder.strip():
            return placeholder.strip()

        name = element.get_attribute("name") or ""
        if name.strip():
            return name.replace("_", " ").replace("-", " ").strip()
    except Exception:
        pass
    return ""


def _is_required(element: Any) -> bool:
    try:
        if element.get_attribute("required") is not None:
            return True
        if element.get_attribute("aria-required") == "true":
            return True
    except Exception:
        pass
    return False


def _fill_page(page: Any, answers: dict[str, Any]) -> list[FilledField]:
    missing: list[FilledField] = []

    inputs = page.locator("input, select, textarea").all()
    for el in inputs:
        try:
            input_type = (el.get_attribute("type") or "text").lower()
            if input_type in _SKIP_INPUT_TYPES:
                continue
            if not el.is_visible():
                continue

            tag = el.evaluate("el => el.tagName.toLowerCase()")
            label = _get_label_for_element(page, el)
            if not label:
                continue

            required = _is_required(el)
            answer = _best_answer(label, answers)

            if answer is None:
                if required:
                    missing.append(FilledField(
                        label=label,
                        field_type=tag if tag != "input" else input_type,
                        required=True,
                    ))
                continue

            if tag == "select":
                _fill_select(el, answer)
            elif input_type == "checkbox":
                _fill_checkbox(el, answer)
            elif input_type == "radio":
                _fill_radio(page, el, label, answer)
            elif input_type == "file":
                pass
            else:
                el.fill(str(answer))
        except Exception:
            continue

    return missing


def _fill_select(el: Any, answer: Any) -> None:
    answer_str = str(answer).lower().strip()
    options = el.locator("option").all()
    for opt in options:
        opt_text = (opt.inner_text() or "").strip().lower()
        opt_val = (opt.get_attribute("value") or "").strip().lower()
        if opt_text == answer_str or opt_val == answer_str:
            el.select_option(value=opt.get_attribute("value"))
            return
    for opt in options:
        opt_text = (opt.inner_text() or "").strip().lower()
        if answer_str in opt_text or opt_text in answer_str:
            el.select_option(value=opt.get_attribute("value"))
            return


def _fill_checkbox(el: Any, answer: Any) -> None:
    should_check = str(answer).lower() in {"true", "yes", "1", "checked", "on"}
    is_checked = el.is_checked()
    if should_check and not is_checked:
        el.check()
    elif not should_check and is_checked:
        el.uncheck()


def _fill_radio(page: Any, el: Any, label: str, answer: Any) -> None:
    answer_str = str(answer).lower().strip()
    name = el.get_attribute("name") or ""
    if name:
        radios = page.locator(f'input[type="radio"][name="{name}"]').all()
        for radio in radios:
            radio_label = _get_label_for_element(page, radio)
            if radio_label.lower().strip() == answer_str:
                radio.check()
                return
        for radio in radios:
            radio_label = _get_label_for_element(page, radio)
            score = difflib.SequenceMatcher(None, answer_str, radio_label.lower().strip()).ratio()
            if score >= _LABEL_SIMILARITY_THRESHOLD:
                radio.check()
                return


def _click_button_by_text(page: Any, texts: set[str]) -> bool:
    candidates = page.locator("button, [type=submit], [role=button]").all()
    for btn in candidates:
        try:
            if not btn.is_visible():
                continue
            text = (btn.inner_text() or "").strip().lower()
            if text in texts:
                btn.click()
                return True
        except Exception:
            continue
    for btn in candidates:
        try:
            if not btn.is_visible():
                continue
            text = (btn.inner_text() or "").strip().lower()
            for t in texts:
                if t in text:
                    btn.click()
                    return True
        except Exception:
            continue
    return False


def fill_and_submit(page: Any, answers: dict[str, Any], *, max_steps: int = 20) -> FillResult:
    all_missing: list[FilledField] = []

    for _ in range(max_steps):
        missing = _fill_page(page, answers)
        all_missing = missing

        if missing:
            return FillResult(submitted=False, missing_fields=missing)

        if _click_button_by_text(page, _SUBMIT_BUTTON_TEXTS):
            try:
                page.wait_for_load_state("networkidle", timeout=10_000)
            except Exception:
                pass
            return FillResult(submitted=True)

        if _click_button_by_text(page, _NEXT_BUTTON_TEXTS):
            try:
                page.wait_for_load_state("networkidle", timeout=10_000)
            except Exception:
                pass
            continue

        break

    raise DOMFillError("Could not find Submit or Next button on the page")
