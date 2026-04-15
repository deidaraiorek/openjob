---
title: feat: Real Playwright browser drivers for Workday, iCIMS, Jobvite, and generic career pages + remove API key requirement from Greenhouse/Lever
type: feat
status: active
date: 2026-04-10
origin: docs/plans/2026-04-09-003-feat-browser-drivers-and-universal-career-page-plan.md
---

# feat: Real Playwright browser drivers + keyless Greenhouse/Lever submissions

## Overview

The browser driver scaffolding (dispatch routing, credential wiring, blocker classification, event logging, artifact persistence) is in place for Workday, iCIMS, Jobvite, and generic career pages. All four currently raise `runner_not_configured` immediately because their `inspect_flow` / `submit_flow` callables are stubs. This plan replaces those stubs with real Playwright sync API implementations.

It also removes the `api_key` hard requirement from Greenhouse and Lever submissions. Both platforms accept unauthenticated POSTs on public job boards — the `api_key` field in `metadata_json` was never populated by the discovery pipeline anyway, so live submissions always fail today.

## Problem Frame

Two separate blockers prevent end-to-end application runs:

1. **Browser drivers are stubs** — Workday, iCIMS, Jobvite, and generic career page targets hit `platform_changed` immediately because the default inspect/submit functions raise without launching any browser.
2. **Greenhouse and Lever require an `api_key` that is never collected** — `service.py` reads `apply_target.metadata_json["api_key"]` for both. Discovery never writes this key. Every Greenhouse and Lever submission therefore KeyErrors or sends unauthenticated requests that fail.

## Requirements Trace

- R1. Playwright must be installed as a declared dependency with its Chromium binary.
- R2. Each browser driver must open a persistent browser context using `ensure_profile_dir`, inject credentials at fill time (not before), and close the context in a `finally` block.
- R3. Workday driver must detect tenant mode (conversational vs standard form) and surface it as `inspection.mode` in the event log.
- R4. iCIMS driver always expects a credential; it navigates to the tenant login page, fills email + password, waits for redirect to the job form, then extracts questions.
- R5. Jobvite driver attempts guest flow first; falls back to credentialed login if a password gate is detected.
- R6. Generic career page driver: Phase 1 DOM extraction → Phase 2 LLM field mapping → Phase 3 form fill. Login walls surface as `action_needed`.
- R7. Greenhouse and Lever submissions must work without an `api_key` — remove the auth parameter from both `submit_application` functions.
- R8. `platform_matrix.py` `implemented=True` is set per-platform only after that platform's driver passes its test suite.
- R9. All browser drivers must be fully testable without a live browser using the injectable callable pattern already in place.
- R10. Playwright and its Chromium binary must be installable in the Docker container (headless, `channel="chromium"`, `--no-sandbox`, `--disable-dev-shm-usage`).

## Scope Boundaries

- This plan does **not** implement MFA auto-solve, CAPTCHA bypass, or anti-bot stealth libraries.
- This plan does **not** add Playwright E2E tests against live ATS sites — all tests use injected stub callables.
- Selector strategies are implementation details; the plan establishes the driver lifecycle shape and key decision points. Exact selectors will be found by the implementer using Playwright Inspector against real pages.
- This plan does **not** change how application accounts are created or encrypted.
- File upload (resume) via browser is deferred — the plan notes where it slots in but does not specify selectors.

## Context & Research

### Relevant Code and Patterns

- **`backend/app/integrations/linkedin/apply.py`** — canonical `InspectFn`/`SubmitFn` callable injection pattern. Every new driver replicates this shape.
- **`backend/app/integrations/linkedin/session_store.py`** — `ensure_profile_dir(account_id, source_key)` builds `{playwright_profile_dir}/account-{id}/{slug}/`. Call with platform name as `source_key`.
- **`backend/app/integrations/linkedin/artifacts.py`** — `persist_artifacts(run_id, {"screenshot": bytes, "page_html": str})`. Artifact kinds must match existing extension map.
- **`backend/app/integrations/linkedin/blockers.py`** — `_contains_marker(page_text, markers)` pattern for page-content-based classification. Reuse in all new drivers.
- **`backend/app/integrations/workday/apply.py`** — stub with correct `InspectFn(target, profile_dir, credential)` / `SubmitFn(target, profile_dir, answers, credential)` signatures.
- **`backend/app/integrations/icims/apply.py`**, **`backend/app/integrations/jobvite/apply.py`**, **`backend/app/integrations/generic_career_page/apply.py`** — same stub pattern.
- **`backend/app/integrations/generic_career_page/field_extractor.py`** — `extract_form_fields(page: Any)` already calls `page.evaluate(js)`. The `page` parameter typed as `Any` avoids hard Playwright import.
- **`backend/app/domains/applications/platform_matrix.py`** — `implemented=False` for all four new platforms; flip per-platform after tests pass.
- **`backend/app/domains/application_accounts/service.py`** — `decrypt_secret(ciphertext)` returns plaintext. Never log the result.
- **`backend/app/config.py`** — `playwright_profile_dir`, `playwright_artifact_dir` settings already exist.
- **`backend/app/integrations/greenhouse/apply.py`** — `submit_application(board_token, job_post_id, api_key, payload)`. Remove `api_key` parameter and `auth=` from the httpx call.
- **`backend/app/integrations/lever/apply.py`** — `submit_application(posting_id, api_key, payload)`. Same fix.
- **`backend/tests/tasks/test_linkedin_retry_and_escalation.py`** — authoritative test pattern: inject `lambda *_: WorkdayInspection(...)` or `lambda *_: (_ for _ in ()).throw(WorkdayAutomationError(...))`.

### External References

- Playwright Python sync API: `playwright.sync_api.sync_playwright`, `launch_persistent_context`
- Recommended headless mode 2026: `channel="chromium"`, `headless=True` (real Chrome binary, not headless shell)
- Chromium args required in Docker/Celery: `--no-sandbox`, `--disable-dev-shm-usage`, `--disable-blink-features=AutomationControlled`
- Context init script to suppress `navigator.webdriver`: `context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")`
- Navigation wait: `page.wait_for_load_state("domcontentloaded")` — never `"networkidle"` on ATS pages
- Default timeout override: `context.set_default_timeout(15_000)` to prevent Celery worker blocking

## Key Technical Decisions

- **Sync Playwright API, not async.** The entire service layer — Celery tasks, route handlers, `execute_*_application_run` — is synchronous. Using async Playwright would require a new event loop per task and break the existing architecture. Sync API maps directly.

- **`launch_persistent_context` over `new_context`.** Persistent contexts save cookies/localStorage to `profile_dir` between runs, enabling session re-use without re-login on subsequent runs. This is the pattern `session_store.py` was designed to support.

- **Playwright added as an optional dependency group, not a hard runtime dependency.** The service layer already handles `runner_not_configured` gracefully when no `inspect_flow` is passed. Installing Playwright only on workers that actually run browser tasks prevents bloating API-only deployments. In `pyproject.toml`, add it to `[project.optional-dependencies]` under a `browser` group.

- **One shared `browser_context.py` helper, not copy-pasted boilerplate in each driver.** Opening a persistent context with the correct Chromium args, timeout defaults, and init script is identical across all four drivers. Extract it to `backend/app/integrations/browser_context.py` so drivers import one function.

- **Login detection uses layered checks: URL pattern → page text → structural selector probe.** No single check is reliable across all ATS tenants. URL check is cheapest; page text scan reuses the existing `_contains_marker` pattern from `linkedin/blockers.py`; structural probe (`input[type=password]` present + no visible apply form) is the fallback.

- **Workday mode detection is runtime-only, not persisted.** The driver's `InspectFn` checks for Workday's conversational AI apply interface vs. standard form. The detected mode is logged in the event payload as `workday_mode` but not written back to `ApplyTarget.metadata_json`. Persisting it would require a migration and creates stale-data risk for tenants that switch modes.

- **Generic career page field mapping uses `groq_model` setting with structured output.** The existing `map_fields_with_llm` function in `generic_career_page/apply.py` is already wired; it just needs the `groq_api_key` / `openai_api_key` from settings. No new LLM infrastructure needed.

- **Remove `api_key` from Greenhouse and Lever without a fallback.** Greenhouse's public board API (`boards-api.greenhouse.io`) and Lever's public apply endpoint (`api.lever.co/v0/postings`) both accept unauthenticated POSTs for public job boards. The `api_key` field was never populated by discovery — removing it from `submit_application` makes the code match actual behavior. If a private board later requires auth, it will surface as an HTTP 401 which classifies as `action_needed`.

## Open Questions

### Resolved During Planning

- **Should Playwright be a hard or optional dependency?** Optional — listed under `[project.optional-dependencies] browser`. This keeps the API service image lean and avoids downloading Chrome on every deploy.
- **Sync or async Playwright?** Sync — the entire stack is synchronous.
- **Should credential decryption happen inside the driver or in the service layer?** Already resolved in the previous plan: service layer passes plaintext `credential` to `execute_*_application_run`. Drivers receive it as a parameter, never call `decrypt_secret` themselves.
- **When does `implemented=True` get set?** Per-platform, at the end of each driver's implementation unit, after its test suite passes.

### Deferred to Implementation

- **Exact CSS selectors for Workday, iCIMS, Jobvite forms.** These must be discovered using Playwright Inspector (`playwright codegen`) against real tenant pages. The plan establishes the detection strategy and lifecycle; selectors are implementation detail.
- **Whether Workday conversational AI apply requires a different submit path.** If conversational apply exposes a structured API rather than a DOM form, the driver's `SubmitFn` may need to POST JSON instead of filling fields. Deferred until the tenant page is inspected.
- **File upload (resume) selector strategies.** Each platform handles file inputs differently. The plan notes where file fields slot in but defers selector specifics.
- **Celery worker `--max-tasks-per-child` tuning.** Setting this prevents orphaned Chrome subprocesses after worker exceptions. The right value depends on memory profile — deferred to deployment config.

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

```
browser_context.py
  open_persistent_context(profile_dir) → (pw, context)
    - launch_persistent_context(channel="chromium", headless=True, args=[...])
    - context.set_default_timeout(15_000)
    - context.add_init_script("navigator.webdriver = undefined")
    - returns (pw_instance, context) for caller to close in finally

Each driver's InspectFn:
  pw, context = open_persistent_context(profile_dir)
  try:
    page = context.new_page()
    page.goto(target.destination_url)
    page.wait_for_load_state("domcontentloaded")
    detect_login_wall(page)  → raises PlatformAutomationError if blocked
    fill_login_if_needed(page, credential)
    questions = extract_questions(page)
    artifacts = {"screenshot": page.screenshot(), "page_html": page.content()}
    return PlatformInspection(step="...", questions=questions, artifacts=artifacts)
  finally:
    context.close()
    pw.stop()

Login wall detection (layered):
  1. URL contains "login" / "signin" / "auth" → login_required
  2. page.content() contains LOGIN_SIGNAL strings → login_required
  3. input[type=password] present AND no visible apply fields → login_required

Workday mode detection (inside InspectFn):
  - Look for conversational AI interface markers (chat widget, "Apply with AI" button)
  - If found: set inspection.mode = "conversational"
  - Else if standard form fields present: set inspection.mode = "public_form"
  - Else if login form: raise WorkdayAutomationError(code="login_required")
```

## Implementation Units

- [x] **Unit 1: Add Playwright dependency and shared browser context helper**

**Goal:** Install Playwright as an optional dependency, add it to `pyproject.toml`, and create the shared `open_persistent_context` helper that all four drivers will use.

**Requirements:** R1, R2, R10

**Dependencies:** None.

**Files:**
- Modify: `backend/pyproject.toml` — add `playwright>=1.40` to `[project.optional-dependencies]` under a `browser` group
- Create: `backend/app/integrations/browser_context.py`
- Test: `backend/tests/integrations/test_browser_context.py`

**Approach:**
- `open_persistent_context(profile_dir: Path, *, headless: bool = True) -> tuple[Any, Any]` — returns `(pw, context)`. Caller is responsible for closing both in a `finally` block.
- Chromium args: `--no-sandbox`, `--disable-dev-shm-usage`, `--disable-blink-features=AutomationControlled`.
- `channel="chromium"` for real Chrome binary (new headless mode).
- `context.set_default_timeout(15_000)`, `context.set_default_navigation_timeout(20_000)`.
- `context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")`.
- The function imports `sync_playwright` inside the function body (not at module level) so the module can be imported even when `playwright` is not installed — the `runner_not_configured` default stubs will still fire correctly.

**Patterns to follow:**
- `backend/app/integrations/linkedin/session_store.py` — how profile dirs are built and passed.

**Test scenarios:**
- Happy path: `open_persistent_context` with a `tmp_path` profile dir returns a non-None tuple — verified by mocking `sync_playwright` to return a fake object with `.start()`, `.chromium.launch_persistent_context()`.
- Edge case: calling with a non-existent profile dir raises no error (Playwright creates it).
- Error path: if `playwright` package is not installed, importing `browser_context.py` does not raise `ImportError` — the import inside the function body defers the failure to call time.

**Verification:**
- `backend/app/integrations/browser_context.py` is importable without Playwright installed.
- The helper is used by at least one driver in subsequent units without duplicating Chromium arg setup.

---

- [x] **Unit 2: Remove API key requirement from Greenhouse and Lever**

**Goal:** Make Greenhouse and Lever submissions work without an `api_key` in `metadata_json`.

**Requirements:** R7

**Dependencies:** None (can land before or after browser units).

**Files:**
- Modify: `backend/app/integrations/greenhouse/apply.py`
- Modify: `backend/app/integrations/lever/apply.py`
- Modify: `backend/app/domains/applications/service.py` — remove `api_key` reads from `_default_submit`
- Test: `backend/tests/integrations/test_greenhouse_apply.py` (extend or create)
- Test: `backend/tests/integrations/test_lever_apply.py` (extend or create)

**Approach:**
- `greenhouse/apply.py`: remove `api_key` parameter from `submit_application`; remove `auth=httpx.BasicAuth(api_key, "")` from the `httpx.post` call.
- `lever/apply.py`: same — remove `api_key` parameter and `auth=(api_key, "")`.
- `service.py` `_default_submit`: remove the `api_key` reads from `apply_target.metadata_json` for both target types. The call sites become `greenhouse_apply.submit_application(board_token, job_post_id, submission_payload)` and `lever_apply.submit_application(posting_id, submission_payload)`.
- If a private board returns HTTP 401, the `RetryableApplyError` catch block in `_default_submit` will surface it as `action_needed` — no special handling needed.

**Patterns to follow:**
- `backend/app/integrations/ashby/` — Ashby submit has no API key; this is the target shape for both Greenhouse and Lever.

**Test scenarios:**
- Happy path: `submit_application` for Greenhouse makes an httpx POST without `auth=` and returns parsed JSON — verified with `respx` or `httpx` mock.
- Happy path: `submit_application` for Lever same.
- Error path: HTTP 401 response from Greenhouse raises `httpx.HTTPStatusError`, which `service.py` catches as `RetryableApplyError` and logs as `action_needed`.
- Integration: `execute_application_run` for a Greenhouse target with no `api_key` in `metadata_json` reaches the submit call without `KeyError`.

**Verification:**
- Existing Greenhouse and Lever tests pass with no `api_key` in any fixture's `metadata_json`.
- No `api_key` reference remains in `greenhouse/apply.py` or `lever/apply.py`.

---

- [x] **Unit 3: Workday browser driver (real implementation)**

**Goal:** Replace the `_default_inspect` / `_default_submit` stubs in `workday/apply.py` with real Playwright flows. Set `implemented=True` in the platform matrix.

**Requirements:** R2, R3, R8, R9

**Dependencies:** Unit 1

**Files:**
- Modify: `backend/app/integrations/workday/apply.py` — replace `_default_inspect` and `_default_submit`
- Modify: `backend/app/domains/applications/platform_matrix.py` — set `implemented=True` for `workday`
- Test: `backend/tests/integrations/test_workday_apply.py` (create)

**Approach:**
- `_default_inspect(apply_target, profile_dir, credential)`:
  - Open context via `open_persistent_context(profile_dir)` in `try/finally`.
  - `page.goto(apply_target.destination_url)` + `wait_for_load_state("domcontentloaded")`.
  - Layered login wall check (URL → page text → selector probe). If login wall and no credential: raise `WorkdayAutomationError(code="login_required")`.
  - If credential present and login wall detected: fill email + password, submit, wait for redirect.
  - Detect mode: look for conversational AI apply markers in page content/DOM. Set `mode = "conversational"` or `mode = "public_form"`.
  - Extract form questions from the visible application form.
  - Capture `page.screenshot()` and `page.content()` into `artifacts`.
  - Return `WorkdayInspection(step="inspect", mode=mode, questions=questions, artifacts=artifacts)`.
- `_default_submit(apply_target, profile_dir, answers_by_key, credential)`:
  - Re-open context (persistent context re-uses saved session cookies from inspect phase).
  - Navigate to apply URL, fill each answer into the corresponding field using `answers_by_key`.
  - Submit the form, wait for confirmation page.
  - Return `WorkdaySubmission(step="submit", artifacts={"screenshot": ..., "page_html": ...})`.

**Patterns to follow:**
- `backend/app/integrations/linkedin/apply.py` — complete lifecycle template.
- `backend/app/integrations/browser_context.py` — open/close pattern.
- `backend/app/integrations/linkedin/blockers.py` — `_contains_marker` for page text classification.

**Test scenarios:**
- Happy path: inject `inspect_flow` stub returning `WorkdayInspection(mode="public_form", questions=[...])` → `execute_workday_application_run` logs `workday_mode: public_form` in the `questions_fetched` event.
- Happy path: inject `inspect_flow` + `submit_flow` stubs → `run.status == "submitted"`.
- Error path: inject `inspect_flow` that raises `WorkdayAutomationError(code="login_required")` → `run.status == "action_needed"`, event payload has `code: "login_required"`.
- Error path: `WorkdayAutomationError(code="mfa_required")` → `run.status == "action_needed"`.
- Error path: `WorkdayAutomationError(code="selector_missing")` → `run.status == "platform_changed"`.
- Edge case: `_default_inspect` with no `inspect_flow` injected → raises `runner_not_configured` → `run.status == "platform_changed"`.
- Integration: credential passed as non-None flows through `execute_workday_application_run` into the stub `inspect_flow` without appearing in any event payload.

**Verification:**
- All test scenarios above pass without launching a browser.
- `platform_matrix.py` `implemented=True` for workday.
- `_default_inspect` and `_default_submit` contain real Playwright code (not stubs), verified by inspection.

---

- [x] **Unit 4: iCIMS browser driver (real implementation)**

**Goal:** Replace stubs in `icims/apply.py` with real Playwright flows. iCIMS always requires a credential. Set `implemented=True`.

**Requirements:** R2, R4, R8, R9

**Dependencies:** Unit 1

**Files:**
- Modify: `backend/app/integrations/icims/apply.py`
- Modify: `backend/app/domains/applications/platform_matrix.py` — set `implemented=True` for `icims`
- Test: `backend/tests/integrations/test_icims_apply.py` (create)

**Approach:**
- iCIMS login flow: navigate to tenant portal login page (URL pattern: `*.icims.com/jobs/<id>/login`), fill email + password using `get_by_label` or `locator("input[name='username']")` / `locator("input[type='password']")`, submit, wait for redirect to job application page.
- After login, extract form questions from the application form fields.
- On login failure (URL stays on login page or error message appears): raise `ICIMSAutomationError(code="login_failed")`.
- `execute_icims_application_run` already calls `record_login_failure` on the application account when `login_failed` is caught in the service layer — confirm this wiring is in place.

**Patterns to follow:**
- Same as Workday driver (Unit 3). iCIMS is structurally identical but always login-required.

**Test scenarios:**
- Happy path: stub `inspect_flow` returning `ICIMSInspection(questions=[...])` + credential → `run.status == "submitted"` with stub submit.
- Error path: `ICIMSAutomationError(code="login_failed")` → `run.status == "action_needed"`.
- Error path: `ICIMSAutomationError(code="account_locked")` → `run.status == "action_needed"`.
- Error path: `ICIMSAutomationError(code="runner_not_configured")` (no inject) → `run.status == "platform_changed"`.
- Integration: after `login_failed`, `application_account.credential_status == "login_failed"` — requires a test that actually calls `execute_icims_application_run` through `execute_application_run` and checks the DB record.

**Verification:**
- Tests pass without a browser.
- `platform_matrix.py` `implemented=True` for icims.

---

- [x] **Unit 5: Jobvite browser driver (real implementation)**

**Goal:** Replace stubs in `jobvite/apply.py` with real Playwright flows. Attempt guest flow first, fall back to credentialed login.

**Requirements:** R2, R5, R8, R9

**Dependencies:** Unit 1

**Files:**
- Modify: `backend/app/integrations/jobvite/apply.py`
- Modify: `backend/app/domains/applications/platform_matrix.py` — set `implemented=True` for `jobvite`
- Test: `backend/tests/integrations/test_jobvite_apply.py` (create)

**Approach:**
- Navigate to apply URL. If no login gate detected (no password field, apply form visible directly): proceed as guest — fill form, submit.
- If login gate detected and `credential` is non-None: fill email + password, submit, wait for redirect to job form.
- If login gate detected and `credential` is None: raise `JobviteAutomationError(code="login_required")`.
- Login failure detection: post-submit, if still on login page or error message visible → raise `JobviteAutomationError(code="login_failed")`.

**Patterns to follow:**
- Same driver lifecycle shape as Workday and iCIMS.

**Test scenarios:**
- Happy path (guest): stub `inspect_flow` with `credential=None` returning `JobviteInspection(questions=[...])` → succeeds.
- Happy path (credentialed): stub `inspect_flow` with `credential="plaintext"` → succeeds.
- Error path: login gate + no credential → `run.status == "action_needed"` with `code="login_required"`.
- Error path: `login_failed` → `run.status == "action_needed"`.
- Edge case: `_default_inspect` with no inject → `runner_not_configured` → `platform_changed`.

**Verification:**
- Tests pass without a browser.
- `platform_matrix.py` `implemented=True` for jobvite.

---

- [x] **Unit 6: Generic career page driver (real implementation)**

**Goal:** Replace stubs in `generic_career_page/apply.py` with real Playwright flows. Phase 1: DOM extraction. Phase 2: LLM field mapping. Phase 3: form fill. Set `implemented=True`.

**Requirements:** R2, R6, R8, R9

**Dependencies:** Unit 1

**Files:**
- Modify: `backend/app/integrations/generic_career_page/apply.py`
- Modify: `backend/app/integrations/generic_career_page/field_extractor.py` — wire `page` parameter to real Playwright `Page` type (still typed `Any` for optional import; no functional change needed)
- Modify: `backend/app/domains/applications/platform_matrix.py` — set `implemented=True` for `generic_career_page`
- Test: `backend/tests/integrations/test_generic_career_page_apply.py` (create)

**Approach:**
- `_default_inspect(apply_target, profile_dir, credential)`:
  - Open context, navigate to URL.
  - Login wall check: if email + password inputs present with no visible job form → raise `GenericCareerPageError(code="login_wall_detected")`.
  - If `credential` present and login wall: attempt login (generic: fill first email field, first password field, click submit button). This is best-effort only.
  - Call `extract_form_fields(page)` from `field_extractor.py` to get the structured field list.
  - If empty field list returned: raise `GenericCareerPageError(code="no_form_found")`.
  - Call `map_fields_with_llm(form_fields, settings=settings)` to get `{input_name: answer_key}` mapping.
  - Build synthetic `ApplyQuestion` list from the mapping — one question per mapped field, `key=answer_key`, `prompt_text=field["label"]`, `field_type=field["type"]`, `required=field["required"]`.
  - Unmapped required fields also become questions with `key=field["input_name"]` so `ensure_question_task` picks them up for human review.
  - Return `GenericCareerPageInspection(step="inspect", questions=questions, artifacts=...)`.
- `_default_submit`: fill each form field by `input_name` using `page.locator(f"[name='{name}']").fill(value)`. Click the submit button. Wait for navigation or success indicator.

**Patterns to follow:**
- `backend/app/integrations/linkedin/apply.py` — lifecycle.
- `backend/app/integrations/generic_career_page/field_extractor.py` — `FakePage` pattern for unit tests.
- `backend/app/integrations/openai/job_relevance.py` — LLM call pattern (structured output, `groq_api_key` / `openai_api_key`).

**Test scenarios:**
- Happy path: `FakePage.evaluate()` returns a two-field list → `extract_form_fields` returns those fields → stub LLM maps them → `inspect_flow` returns two questions.
- Happy path: AI mapping returns confident mapping for 3/5 fields → 2 unmapped fields become question tasks → `run.status == "blocked_missing_answer"`.
- Error path: login wall detected → `run.status == "action_needed"` with `code="login_wall_detected"`.
- Error path: no form found (empty field list) → `run.status == "platform_changed"` with `code="no_form_found"`.
- Error path: `runner_not_configured` → `platform_changed`.
- Integration: `map_fields_with_llm` called with a stub that returns `{"fname": "first_name"}` → synthetic `ApplyQuestion(key="first_name", ...)` created correctly.

**Verification:**
- `extract_form_fields(FakePage())` returns expected structure in a unit test with no browser.
- All test scenarios pass.
- `platform_matrix.py` `implemented=True` for generic_career_page.

---

- [x] **Unit 7: Add optional playwright settings to config**

**Goal:** Add any missing Playwright-related settings to `Settings` so drivers can tune headless mode, timeout, and binary path without code changes.

**Requirements:** R1, R10

**Dependencies:** Unit 1

**Files:**
- Modify: `backend/app/config.py`

**Approach:**
- Add `playwright_headless: bool = True` — allows running headed for local debugging without code change.
- Add `playwright_timeout_ms: int = 15_000` — passed to `context.set_default_timeout()` in `browser_context.py`.
- Both have sensible defaults so no `.env` changes are required for existing deployments.
- `playwright_profile_dir` and `playwright_artifact_dir` already exist — no change.

**Test scenarios:**
- Happy path: `Settings()` with no env overrides has `playwright_headless=True` and `playwright_timeout_ms=15_000`.
- Edge case: `Settings(playwright_headless=False)` returns `headless=False` — used to verify `browser_context.py` passes the setting through.

**Verification:**
- `browser_context.py` reads `settings.playwright_headless` and `settings.playwright_timeout_ms` — no hardcoded values left in the helper.

## System-Wide Impact

- **Interaction graph:** `execute_application_run` in `service.py` already dispatches to all four new drivers. The `ensure_target_ready` gate will now pass Workday/iCIMS/Jobvite targets through (once `implemented=True`). The only new runtime path is Chrome subprocess launch inside Celery workers.
- **Error propagation:** All browser `AutomationError` subtypes are caught in the respective `execute_*_application_run` function — they never propagate as unhandled exceptions to the service layer or HTTP routes. The `run.status` field absorbs the outcome.
- **State lifecycle risks:** The `context.close()` / `pw.stop()` calls in `finally` blocks are the single most important correctness requirement. A missing `finally` leaves Chrome subprocesses alive until the Celery worker process recycles. `--max-tasks-per-child` on Celery workers provides the safety net.
- **Credential safety:** The plaintext `credential` parameter must never appear in `_log_event` payloads, exception messages, or artifact HTML. The `redact_payload` function in `applications/redaction.py` handles answer dicts — verify it covers any dict that might contain the credential.
- **API surface parity:** Greenhouse and Lever `submit_application` signatures change (drop `api_key`). Any callers outside `service.py` (e.g., tests with direct `submit_application` calls) must be updated.
- **Unchanged invariants:** The LinkedIn driver is not modified. Direct-API platforms (Ashby, SmartRecruiters) are not affected. The `ApplyTargetCandidate` extraction from Unit 1 of the previous plan remains in place.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Playwright not available in Docker image | Add `playwright install --no-shell chromium` to Dockerfile; document in README |
| Chrome subprocess leak on Celery worker | Always use `try/finally` — never rely on `with` blocks across task boundaries; set `--max-tasks-per-child=50` |
| ATS DOM selectors drift after this plan lands | Each driver uses `selector_missing` / `platform_changed` blocker code; run logs surface it immediately |
| Workday anti-bot blocking headless Chrome | Use `channel="chromium"` + `disable-blink-features=AutomationControlled` + `navigator.webdriver` suppression; if still blocked, surface as `captcha_required` |
| iCIMS login failure locking the account | `record_login_failure` sets `credential_status="login_failed"` after first failure; `ensure_target_ready` blocks all subsequent attempts until user rotates password |
| Generic career page LLM mapping hallucinating wrong field mappings | LLM instructed to skip uncertain fields; unmapped fields become question tasks; worst outcome is `blocked_missing_answer`, not a wrong submission |
| Greenhouse/Lever private boards rejecting unauthenticated submissions | HTTP 401 → caught as `RetryableApplyError` → `action_needed` event; user sees it in the action queue |

## Sources & References

- **Origin document:** [docs/plans/2026-04-09-003-feat-browser-drivers-and-universal-career-page-plan.md](docs/plans/2026-04-09-003-feat-browser-drivers-and-universal-career-page-plan.md)
- Related code: `backend/app/integrations/linkedin/apply.py`
- Related code: `backend/app/integrations/browser_context.py` (to be created)
- Related code: `backend/app/integrations/greenhouse/apply.py`
- Related code: `backend/app/integrations/lever/apply.py`
- Related code: `backend/app/domains/applications/platform_matrix.py`
- Related code: `backend/app/config.py`
