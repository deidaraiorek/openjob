from __future__ import annotations

from pathlib import Path
from typing import Any


_CHROMIUM_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-blink-features=AutomationControlled",
]

_NAVIGATOR_WEBDRIVER_SCRIPT = (
    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
)


_SUBMIT_TEXT_PATTERNS = (
    "submit application",
    "send application",
    "complete application",
    "submit",
    "apply now",
    "apply",
)

_SUBMIT_BUTTON_SELECTORS = [
    "[type=submit]",
    "button[type=submit]",
    "button:not([type])",
    "button[type=button]",
    "[role=button]",
]

_SKIP_ARIA_LABELS = {
    "menu", "navigation", "close", "back", "search", "help",
    "main menu", "hamburger", "toggle",
}


def find_submit_button(page: Any) -> Any | None:
    candidates = page.evaluate("""
        () => {
            const SUBMIT_PATTERNS = [
                "submit application", "send application", "complete application",
                "submit", "apply now", "apply",
            ];
            const SKIP_ARIA = new Set([
                "menu", "navigation", "close", "back", "search", "help",
                "main menu", "hamburger", "toggle",
            ]);
            const selectors = [
                "[type=submit]", "button[type=submit]",
                "button:not([type])", "button[type=button]", "[role=button]",
            ];
            const seen = new Set();
            const results = [];
            for (const sel of selectors) {
                for (const el of document.querySelectorAll(sel)) {
                    if (seen.has(el)) continue;
                    seen.add(el);
                    const rect = el.getBoundingClientRect();
                    if (rect.width === 0 || rect.height === 0) continue;
                    const style = window.getComputedStyle(el);
                    if (style.display === "none" || style.visibility === "hidden" || style.opacity === "0") continue;
                    const aria = (el.getAttribute("aria-label") || "").toLowerCase();
                    if (SKIP_ARIA.has(aria)) continue;
                    const text = (el.innerText || el.textContent || "").trim().toLowerCase();
                    let score = 0;
                    for (let i = 0; i < SUBMIT_PATTERNS.length; i++) {
                        if (text === SUBMIT_PATTERNS[i]) { score = 1000 - i; break; }
                        if (text.includes(SUBMIT_PATTERNS[i])) { score = 500 - i; break; }
                    }
                    results.push({score, text, selector: sel, visible: true});
                }
            }
            results.sort((a, b) => b.score - a.score);
            return results.slice(0, 5).map(r => r.text);
        }
    """)

    if not candidates:
        return None

    for text in candidates:
        text_lower = text.strip().lower()
        for selector in _SUBMIT_BUTTON_SELECTORS:
            locator = page.locator(selector)
            count = locator.count()
            for i in range(count):
                el = locator.nth(i)
                try:
                    el_text = (el.inner_text() or "").strip().lower()
                except Exception:
                    continue
                if el_text == text_lower and el.is_visible():
                    return el

    return None


def open_persistent_context(
    profile_dir: Path,
    *,
    headless: bool = True,
    timeout_ms: int = 15_000,
) -> tuple[Any, Any]:
    from playwright.sync_api import sync_playwright  # deferred — optional dependency

    profile_dir.mkdir(parents=True, exist_ok=True)

    pw = sync_playwright().start()
    context = pw.chromium.launch_persistent_context(
        str(profile_dir),
        channel="chromium",
        headless=headless,
        args=_CHROMIUM_ARGS,
    )
    context.set_default_timeout(timeout_ms)
    context.set_default_navigation_timeout(timeout_ms + 5_000)
    context.add_init_script(_NAVIGATOR_WEBDRIVER_SCRIPT)
    return pw, context
