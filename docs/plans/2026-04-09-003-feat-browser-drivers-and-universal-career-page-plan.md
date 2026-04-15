---
title: feat: Browser drivers for Workday/iCIMS/Jobvite and universal career page autopilot
type: feat
status: active
date: 2026-04-09
origin: docs/plans/2026-04-09-002-feat-platform-matrix-and-application-accounts-plan.md
---

# feat: Browser drivers for Workday/iCIMS/Jobvite and universal career page autopilot

## Overview

Extends the OpenJob autopilot beyond the Phase 1 direct-API platforms (Greenhouse, Lever, Ashby, SmartRecruiters) into three browser-driven ATS families that together cover the bulk of the remaining job market — Workday, iCIMS, and Jobvite — plus a universal "generic career page" driver capable of applying to any company's custom career site (Netflix, Stripe, Apple, etc.).

This plan also fixes the existing circular import (`deduplication → target_resolution → link_classification → deduplication`) that is currently blocking the test suite.

## Problem Frame

After Phase 1, the majority of reachable apply targets in the wild fall into four categories this system cannot yet act on:

1. **Workday** — The largest enterprise ATS. Tenant-specific subdomains (`*.myworkdaysite.com`, `*.myworkdayjobs.com`). Some tenants support conversational/AI apply (no login); others gate the form behind a Workday account login.
2. **iCIMS** — Per-employer candidate profiles with unique login/password per tenant host. The plan doc (`docs/plans/2026-04-09-002`) established this as explicitly account-centric.
3. **Jobvite** — Candidate account registration plus hosted/integrated career-site flows. Varies by employer setup.
4. **Generic career pages** — Custom-built sites (Netflix, Apple, Stripe, etc.) that don't use any recognized ATS. These require AI-driven form detection and field filling.

Additionally, `link_classification.py` currently imports `ApplyTargetCandidate` from `deduplication.py`, which itself imports `target_resolution`, creating a circular module dependency that breaks the test suite import chain.

## Requirements Trace

From `docs/plans/2026-04-09-002-feat-platform-matrix-and-application-accounts-plan.md`:

- **R2-R4:** Discovery must map downstream links into a stable shared platform vocabulary — the platform matrix must cover Workday, iCIMS, Jobvite, and generic career pages.
- **R7-R9:** Preferred apply-target selection must distinguish driver families and readiness states correctly for all new platform families.
- **R15-R20:** Known application credentials must be retrievable at driver execution time without exposing secret values.
- **R21-R26:** Application logs must surface `missing_application_account`, `login_failed`, `mfa_required`, `captcha_required`, and `platform_not_supported` as first-class states.
- **R27-R30:** The portal must surface readiness state for all new families before a run is attempted.
- **R32-R33:** Single-user personal tool — no multi-identity, no team vaults, no per-role resume switching.

New requirement added by user:
- **R34:** The system must be extensible to arbitrary company career pages with no recognized ATS, using AI-assisted form detection and field filling.

## Scope Boundaries

- This plan does **not** implement Playwright browser automation from scratch — it reuses `playwright_profile_dir`, `artifacts.py`, `session_store.py`, and the blocker classification pattern from the LinkedIn integration.
- This plan does **not** add new ATS source types for ingest discovery for Workday/iCIMS/Jobvite — those platforms are primarily reached via resolved outbound links, not direct job board APIs.
- This plan does **not** implement MFA auto-solve, CAPTCHA bypass, or email-code interception. These are surfaced as `action_needed` blocker states.
- This plan does **not** add multi-user or team-scoped credential sharing.
- The generic career page driver is **not** guaranteed to work on every arbitrary site. Sites with multi-step wizards, anti-bot measures beyond simple rate-limiting, or deeply custom DOM structures may remain `action_needed`. The driver's job is best-effort AI-assisted form filling with a clear failure path.
- This plan does **not** redesign the question-answer memory system — existing `resolve_questions` and `ensure_question_task` machinery is reused as-is.

## Context & Research

### Relevant Code and Patterns

- **LinkedIn driver as the primary template:** `backend/app/integrations/linkedin/apply.py` defines the complete browser driver lifecycle — `InspectFn`/`SubmitFn` callables, `LinkedInInspection`/`LinkedInSubmission` dataclasses, artifact persistence, blocker classification, and `execute_linkedin_application_run`. Every new browser driver should follow this exact shape.
- **`blockers.py`:** `LinkedInAutomationError` with `code`, `step`, `message`, `artifacts` fields; `classify_linkedin_exception` returns a structured decision. Each new platform needs its own equivalent blocker taxonomy.
- **`session_store.py`:** `ensure_profile_dir(account_id, source_key)` creates a Playwright profile directory scoped per account and integration. Workday/iCIMS/Jobvite drivers pass their platform name as `source_key`.
- **`artifacts.py`:** `persist_artifacts(run_id, artifacts)` saves screenshots, HTML, and traces. All new drivers use this identically.
- **`application_accounts/service.py`:** `find_application_account_for_target` and `decrypt_secret` provide the credential lookup pattern. At driver execution time, the browser driver calls `decrypt_secret(record.secret_ciphertext)` to get the plaintext password — this is the only place the secret leaves encrypted storage.
- **`driver_registry.py`:** `resolve_driver(target)` currently hard-codes known target types. It must be extended to return typed driver keys for Workday, iCIMS, Jobvite, and `generic_career_page`.
- **`platform_matrix.py`:** Already defines all four new families with correct `driver_family`, `credential_policy`, and host patterns. Setting `implemented=True` is the gate that allows `ensure_target_ready` to pass targets through.
- **`link_classification.py`:** The circular import is caused by importing `ApplyTargetCandidate` from `deduplication` at module load. `ApplyTargetCandidate` is only referenced in the `ClassifiedTarget.as_candidate()` method body — it can be moved to a `TYPE_CHECKING` guard plus a local import inside the method body.
- **Workday host patterns already in matrix:** `myworkdayjobs.com`, `myworkdaysite.com`, `workday.com`, `workdayjobs.com`.

### External References

From `docs/plans/2026-04-09-002`:
- Workday conversational AI apply: `https://www.workday.com/en-be/products/conversational-ai/candidate-experience.html`
- iCIMS candidate portal guide: `https://community.icims.com/articles/HowTo/Candidate-Guide-to-the-iCIMS-Talent-Platform`
- Jobvite candidate registration: `https://app.jobvite.com/info/register.aspx`
- OWASP secrets management: `https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html`

For the generic career page driver:
- Playwright Python docs for page inspection and form interaction patterns
- LLM structured output (already available via `groq_api_key` + `openai_api_key` in `app.config`) for field-label-to-answer-key mapping

## Key Technical Decisions

- **Reuse the LinkedIn driver shape exactly for all browser drivers.** Each platform gets `Inspection`/`Submission` dataclasses, `InspectFn`/`SubmitFn` callables, `execute_<platform>_application_run`, and a `blockers.py`. This makes the driver family uniform and testable without Playwright in unit tests.
- **Workday tenant-mode detection happens inside the driver, not in the platform matrix.** The matrix marks Workday as `browser/optional`. The driver's `InspectFn` is responsible for probing whether the tenant uses conversational apply or login-gated flow, setting `metadata["workday_mode"]` on the target for logging. This keeps the platform registry stable and avoids baking runtime-discovered flow shapes into persistent data prematurely.
- **iCIMS and Jobvite credential lookup happens at driver invocation time, not at readiness check time.** `find_application_account_for_target` is already called by `ensure_target_ready`. The driver additionally calls `decrypt_secret` at the moment Playwright needs to type the password — the plaintext never touches the database or event log.
- **Generic career page driver uses a two-phase approach: DOM inspection → AI field mapping → form fill.** Phase 1: Playwright navigates to the apply URL, extracts all form fields (label text, input name/id, field type, required flag) as structured JSON. Phase 2: an LLM call maps each extracted field to the best available answer from the answer store (using the same `resolve_questions` question-matching infrastructure). Phase 3: Playwright types the mapped answers. This avoids needing to pre-define question fingerprints for arbitrary sites — the LLM bridges the gap.
- **`ApplyTargetCandidate` is moved to its own module to break the circular import.** Rather than using `TYPE_CHECKING` (which only defers the import for type checkers, not runtime), the cleanest fix is to move `ApplyTargetCandidate` into a new `backend/app/domains/jobs/apply_target_candidate.py` module that neither `deduplication` nor `link_classification` depends on cyclically. Both modules then import from the new module.
- **The `generic_career_page` family is added to `PLATFORM_FAMILIES` and `PLATFORM_REGISTRY` as a catch-all for unrecognized hosts, with `driver_family="browser"` and `credential_policy="not_needed"` by default.** Sites that are known to require login can override credential policy via `metadata["credential_policy"]`. The generic driver is gated by an explicit `implemented=True` only after the driver itself lands.
- **Workday, iCIMS, and Jobvite are marked `implemented=True` in the platform matrix only when their respective driver units land.** This preserves the existing `platform_not_supported` gate behavior during incremental rollout.
- **Driver registry extended with named driver keys** — `workday_browser`, `icims_browser`, `jobvite_browser`, `generic_career_page` — so `service.py` can dispatch to the right `execute_*` function without another cascade of `if target_type ==` branches.

## Open Questions

### Resolved During Planning

- **Should Workday sub-mode (conversational vs login) be stored on the `ApplyTarget` model?** Not initially. The driver detects it at runtime and logs it as an event payload field. If sub-mode becomes a stable selector (e.g., user can pin a target to a mode), it can be promoted to metadata later.
- **Should the generic career page driver try to auto-detect login requirements?** Yes, but conservatively. If the first page visited is a login wall (detected by looking for email/password input pairs with no visible job form), the driver records `action_needed: login_required` and surfaces it rather than attempting to log in without credentials.
- **Can `ApplyTargetCandidate` be TYPE_CHECKING-only in `link_classification.py`?** No — it is instantiated in `ClassifiedTarget.as_candidate()` at runtime. Moving to a shared module is the right fix.
- **Should generic career page targets use `target_type="generic_career_page"` or `target_type="external_link"` with a platform family in metadata?** Use a dedicated `target_type="generic_career_page"` so the driver registry can dispatch cleanly without metadata inspection.

### Deferred to Implementation

- Exact Playwright selector strategies for each platform — these depend on live DOM inspection and will evolve. The plan establishes the driver shape; selectors are implementation detail.
- Which LLM model to use for generic career page field mapping — the existing `groq_model` setting is a reasonable default, but the implementer should validate response quality for structured field-mapping tasks.
- Whether Jobvite credential scope should be platform-global or tenant-scoped — deferred per the origin plan, to be validated against representative career sites during implementation.
- Rate-limit and backoff tuning per platform — the driver should implement conservative defaults (1 attempt, no auto-retry for login failures); specific thresholds are implementation detail.
- Workday conversational apply API contract — if Workday exposes a structured conversational apply API in 2026, the driver could be upgraded to a direct-API lane. Deferred until confirmed.

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

```
Apply target resolved
        │
        ▼
driver_registry.resolve_driver(target)
        │
        ├─► "direct_api"          → _execute_direct_api_run (Greenhouse/Lever/Ashby/SR)
        ├─► "linkedin_browser"    → execute_linkedin_application_run
        ├─► "workday_browser"     → execute_workday_application_run
        │       │
        │       ├── InspectFn probes tenant: conversational | login_gated
        │       └── if login_gated: decrypt_secret → fill credentials
        ├─► "icims_browser"       → execute_icims_application_run
        │       └── always: find_application_account → decrypt_secret
        ├─► "jobvite_browser"     → execute_jobvite_application_run
        │       └── if account found: decrypt_secret; else: attempt guest flow
        └─► "generic_career_page" → execute_generic_career_page_run
                ├── Phase 1: DOM extraction (form fields → JSON)
                ├── Phase 2: LLM field mapping (fields → answer_keys)
                ├── Phase 3: resolve_questions + form fill
                └── if login wall detected: action_needed

Each browser driver lifecycle:
  inspect_flow(target, profile_dir) → PlatformInspection
      questions: list[ApplyQuestion]
      artifacts: {screenshot, page_html}
      mode: str  (platform-specific sub-mode label)
  submit_flow(target, profile_dir, answers_by_key) → PlatformSubmission
      step: str
      artifacts: {screenshot, ...}
  on exception → PlatformAutomationError(code, step, message, artifacts)
      → classify_<platform>_exception → decision.status
      → persist_artifacts → event log
```

**Generic career page field mapping (AI bridge):**

```
DOM extraction produces:
  [{"label": "First Name", "input_name": "fname", "type": "text", "required": true}, ...]

LLM prompt (structured output):
  "Given these form fields and the available answer keys, return a JSON mapping
   of {input_name: answer_key} for fields you can confidently map.
   Available answer keys: [name, email, phone, linkedin_url, ...]"

LLM returns:
  {"fname": "first_name", "lname": "last_name", "email_address": "email"}

Driver then calls resolve_questions with synthetic ApplyQuestion objects
built from the mapping, falling through to ensure_question_task for unknowns.
```

## Implementation Units

- [ ] **Unit 1: Fix circular import — extract `ApplyTargetCandidate` to shared module**

**Goal:** Unblock the test suite by eliminating the circular import between `deduplication`, `target_resolution`, and `link_classification`.

**Requirements:** Unblocks all downstream units; no requirements number but prerequisite for the entire suite to run.

**Dependencies:** None.

**Files:**
- Create: `backend/app/domains/jobs/apply_target_candidate.py`
- Modify: `backend/app/domains/jobs/deduplication.py` (remove `ApplyTargetCandidate` definition, import from new module)
- Modify: `backend/app/domains/sources/link_classification.py` (remove import from `deduplication`, import from new module)
- Test: `backend/tests/domains/test_platform_matrix.py` (run existing suite to confirm no import errors)

**Approach:**
- Move the `ApplyTargetCandidate` dataclass verbatim into `apply_target_candidate.py`. No other logic moves.
- Both `deduplication.py` and `link_classification.py` import `ApplyTargetCandidate` from the new module.
- No other file changes. The module graph becomes: `link_classification → apply_target_candidate` and `deduplication → apply_target_candidate`, with no cycle.

**Patterns to follow:**
- `backend/app/domains/applications/platform_matrix.py` — standalone module with no upward imports into the `jobs` domain.

**Test scenarios:**
- Happy path: importing `app.domains.jobs.deduplication` and `app.domains.sources.link_classification` in the same process completes without `ImportError` or `circular import` error.
- Happy path: `ApplyTargetCandidate` instances created from `link_classification.ClassifiedTarget.as_candidate()` are the same type as those in `deduplication.DiscoveryCandidate.apply_targets`.
- Integration: the full pytest suite (`backend/tests/`) collects and runs without import failures.

**Verification:**
- `pytest backend/tests/` collects all tests without `ImportError`. The two pre-existing unrelated test failures (`test_deduplication` and `test_job_title_matching`) may remain but no new failures appear.

---

- [ ] **Unit 2: Extend driver registry for browser platforms**

**Goal:** Make `driver_registry.resolve_driver` return typed driver keys for Workday, iCIMS, Jobvite, and `generic_career_page` so `service.py` can dispatch without another `if target_type ==` cascade.

**Requirements:** R7-R9

**Dependencies:** Unit 1

**Files:**
- Modify: `backend/app/domains/applications/driver_registry.py`
- Modify: `backend/app/domains/applications/platform_matrix.py` (add `generic_career_page` to `PLATFORM_FAMILIES` and `PLATFORM_REGISTRY`; add `generic_career_page` to `TARGET_TYPE_PLATFORM_MAP`)
- Test: `backend/tests/domains/test_driver_registry.py` (create)

**Approach:**
- Add `ApplicationDriver` constants: `WORKDAY_BROWSER_DRIVER`, `ICIMS_BROWSER_DRIVER`, `JOBVITE_BROWSER_DRIVER`, `GENERIC_CAREER_PAGE_DRIVER`.
- `resolve_driver` maps `target_type` values: `workday_apply → workday_browser`, `icims_apply → icims_browser`, `jobvite_apply → jobvite_browser`, `generic_career_page → generic_career_page`.
- The `generic_career_page` platform entry in the registry: `driver_family="browser"`, `credential_policy="not_needed"`, `implemented=False` initially, `priority=5` (lowest — only used when nothing else matches), no host patterns (it is the catch-all).
- Keep `external_link` as the existing unrecognized-host catch-all that raises `ValueError` (requires manual action). `generic_career_page` is a different, opt-in target type that is only created when the link classifier or user explicitly selects it.

**Patterns to follow:**
- Existing `resolve_driver` logic in `driver_registry.py` — extend the dispatch chain without redesigning it.

**Test scenarios:**
- Happy path: `resolve_driver` returns `workday_browser` for a target with `target_type="workday_apply"`.
- Happy path: `resolve_driver` returns `icims_browser` for `icims_apply`, `jobvite_browser` for `jobvite_apply`, `generic_career_page` for `generic_career_page`.
- Happy path: existing `greenhouse_apply`, `lever_apply`, `ashby_apply`, `smartrecruiters_apply` still return `direct_api`.
- Happy path: `linkedin_easy_apply` still returns `linkedin_browser`.
- Error path: `external_link` still raises `ValueError`.
- Edge case: a target with `target_type="external_link"` and `metadata["platform_family"]="workday"` still raises (target upgrade required, not auto-promoted).

**Verification:**
- All existing driver registry tests pass. New target types resolve to correct driver keys.

---

- [ ] **Unit 3: Workday browser driver**

**Goal:** Implement a Playwright-compatible browser driver for Workday that handles both the conversational/public apply flow and the login-gated apply flow.

**Requirements:** R7-R9, R21-R26

**Dependencies:** Units 1-2

**Files:**
- Create: `backend/app/integrations/workday/__init__.py`
- Create: `backend/app/integrations/workday/blockers.py`
- Create: `backend/app/integrations/workday/apply.py`
- Modify: `backend/app/domains/applications/service.py` (add `workday_browser` dispatch branch)
- Modify: `backend/app/domains/applications/platform_matrix.py` (`implemented=True` for workday — do this last, after the driver unit is complete)
- Test: `backend/tests/integrations/test_workday_apply.py` (create)

**Approach:**
- `blockers.py`: define `WorkdayAutomationError(code, step, message, artifacts)` and `classify_workday_exception`. Blocker codes: `login_required`, `mfa_required`, `captcha_required`, `selector_missing`, `tenant_not_supported`, `cooldown_required`.
- `apply.py`: follow the LinkedIn driver shape exactly — `WorkdayInspection`, `WorkdaySubmission` dataclasses; `InspectFn`/`SubmitFn` callables; `_default_inspect`/`_default_submit` stubs that raise `WorkdayAutomationError(code="runner_not_configured")`; `execute_workday_application_run(session, *, account, job_id, ...)`.
- Tenant-mode detection inside `InspectFn`: navigate to `apply_target.destination_url`, check DOM for a Workday login form vs. a direct application form. If login form is present and no application account exists for the tenant, raise `WorkdayAutomationError(code="login_required")`. If conversational apply is detected (chat interface), set `inspection.mode = "conversational"`. If a standard form is present, set `inspection.mode = "public_form"`.
- Credential injection: if `mode == "login_gated"` and an application account exists, call `decrypt_secret` and pass the plaintext to the Playwright form fill. The plaintext must not appear in any event log or exception message.
- `service.py` dispatch: in `execute_application_run`, add `elif driver.key == "workday_browser": return execute_workday_application_run(...)`.

**Patterns to follow:**
- `backend/app/integrations/linkedin/apply.py` — complete driver lifecycle template.
- `backend/app/integrations/linkedin/blockers.py` — blocker taxonomy and `classify_*_exception` pattern.
- `backend/app/domains/application_accounts/service.py` `decrypt_secret` — the only place plaintext leaves encrypted storage.

**Test scenarios:**
- Happy path: `_default_inspect` raises `WorkdayAutomationError(code="runner_not_configured")` — driver fails gracefully without Playwright present.
- Happy path: `execute_workday_application_run` with a stub `inspect_flow` that returns `WorkdayInspection(questions=[...], mode="public_form")` proceeds to question resolution and calls `submit_flow`.
- Happy path: a `login_required` error from `inspect_flow` results in `run.status == "action_needed"` with `blocker_type == "login_required"` in the event log.
- Edge case: if `inspect_flow` returns `mode="conversational"`, the driver records the mode in the event log and attempts the conversational flow.
- Error path: `WorkdayAutomationError(code="mfa_required")` results in `run.status == "action_needed"`.
- Error path: `WorkdayAutomationError(code="selector_missing")` results in `run.status == "platform_changed"`.
- Integration: `execute_workday_application_run` follows the same `ApplicationRun` event lifecycle as the LinkedIn driver — `queued`, then `questions_fetched` or the failure event.
- Integration: credential lookup via `find_application_account_for_target` is called when `credential_policy` is `optional` or `tenant_required`; the result is passed to `submit_flow`; the plaintext password never appears in the event log.

**Verification:**
- Workday targets with `target_type="workday_apply"` are dispatched through `execute_workday_application_run`. The driver fails gracefully without Playwright. Credential lookup and secret decryption work end-to-end in an integration test with a stub submit flow.

---

- [ ] **Unit 4: iCIMS account-aware browser driver**

**Goal:** Implement a browser driver for iCIMS that always requires an application account for the tenant host, injects credentials at login time, and surfaces `missing_application_account` before even attempting the browser session.

**Requirements:** R15-R20, R21-R26

**Dependencies:** Units 1-3

**Files:**
- Create: `backend/app/integrations/icims/__init__.py`
- Create: `backend/app/integrations/icims/blockers.py`
- Create: `backend/app/integrations/icims/apply.py`
- Modify: `backend/app/domains/applications/service.py` (add `icims_browser` dispatch branch)
- Modify: `backend/app/domains/applications/platform_matrix.py` (`implemented=True` for icims — do this last)
- Test: `backend/tests/integrations/test_icims_apply.py` (create)

**Approach:**
- `blockers.py`: `iCIMSAutomationError(code, step, message, artifacts)`. Codes: `login_failed`, `mfa_required`, `captcha_required`, `account_locked`, `selector_missing`, `tenant_not_supported`.
- `apply.py`: same LinkedIn driver shape. `iCIMSInspection`, `iCIMSSubmission`. `_default_inspect` raises `iCIMSAutomationError(code="runner_not_configured")`.
- The `InspectFn` always expects an application account to be pre-fetched. The driver receives the decrypted credential as a parameter (not retrieved inside the integration — retrieval happens in the service dispatch layer to keep the integration layer free of database access). Service layer passes `credential=decrypt_secret(record.secret_ciphertext)` into `execute_icims_application_run`.
- If no account exists, `ensure_target_ready` already blocks with `missing_application_account` before the driver is reached.
- Browser flow: navigate to tenant portal login, fill email + password, handle post-login redirect to the job application form.

**Patterns to follow:**
- Same as Workday driver (Unit 3). iCIMS is structurally identical but always login-required, never conversational.

**Test scenarios:**
- Happy path: `execute_icims_application_run` with a stub `inspect_flow` and a pre-stored application account proceeds through question resolution and calls `submit_flow`.
- Happy path: `_default_inspect` fails gracefully with `runner_not_configured`.
- Error path: `iCIMSAutomationError(code="login_failed")` sets `run.status == "action_needed"` and calls `record_login_failure` on the application account record.
- Error path: `iCIMSAutomationError(code="account_locked")` results in `action_needed` with appropriate blocker message.
- Edge case: two iCIMS application accounts for different tenant hosts; the driver receives the credential for the correct tenant host.
- Integration: after a login failure, `application_account.credential_status == "login_failed"` and `last_failure_message` is populated.

**Verification:**
- iCIMS targets with a stored application account dispatch correctly. Login failures update the application account record's credential status. The decrypted password never appears in event logs.

---

- [ ] **Unit 5: Jobvite account-aware browser driver**

**Goal:** Implement a browser driver for Jobvite that attempts a guest flow first and falls back to application account login when one is available.

**Requirements:** R15-R20, R21-R26

**Dependencies:** Units 1-3

**Files:**
- Create: `backend/app/integrations/jobvite/__init__.py`
- Create: `backend/app/integrations/jobvite/blockers.py`
- Create: `backend/app/integrations/jobvite/apply.py`
- Modify: `backend/app/domains/applications/service.py` (add `jobvite_browser` dispatch branch)
- Modify: `backend/app/domains/applications/platform_matrix.py` (`implemented=True` for jobvite — do this last)
- Test: `backend/tests/integrations/test_jobvite_apply.py` (create)

**Approach:**
- Structurally identical to iCIMS driver. Key difference: Jobvite sometimes allows guest apply (no login). The `InspectFn` detects whether a login gate is present. If not gated, proceed without credentials. If gated and an application account exists, inject credentials. If gated and no account exists, raise `JobviteAutomationError(code="login_required")` so the run is surfaced as `action_needed` rather than silently blocked.
- `blockers.py`: `JobviteAutomationError`. Codes: `login_required`, `login_failed`, `mfa_required`, `captcha_required`, `selector_missing`.
- Pass optional `credential` parameter to `execute_jobvite_application_run` — `None` when no account exists, decrypted string when one does.

**Patterns to follow:**
- Same as Workday and iCIMS drivers.

**Test scenarios:**
- Happy path: guest flow (no login gate detected) proceeds to form fill without credentials.
- Happy path: login-gated flow with a stored application account injects credentials and proceeds.
- Error path: login-gated flow without a stored application account raises `login_required`, resulting in `action_needed`.
- Error path: `login_failed` updates the application account credential status.
- Edge case: `_default_inspect` raises `runner_not_configured`.

**Verification:**
- Jobvite targets dispatch correctly in both guest and credentialed modes. The `action_needed` state is surfaced when login is required but no account exists.

---

- [ ] **Unit 6: Generic career page driver**

**Goal:** Implement a best-effort browser driver that can apply to any arbitrary company career page using AI-assisted form detection and field mapping.

**Requirements:** R34 (new), R21-R26

**Dependencies:** Units 1-3

**Files:**
- Create: `backend/app/integrations/generic_career_page/__init__.py`
- Create: `backend/app/integrations/generic_career_page/blockers.py`
- Create: `backend/app/integrations/generic_career_page/field_extractor.py`
- Create: `backend/app/integrations/generic_career_page/apply.py`
- Modify: `backend/app/domains/applications/service.py` (add `generic_career_page` dispatch branch)
- Modify: `backend/app/domains/applications/platform_matrix.py` (`implemented=True` for `generic_career_page` — do this last)
- Test: `backend/tests/integrations/test_generic_career_page_apply.py` (create)

**Approach:**
- **`field_extractor.py`**: given a Playwright `page` object, extract all visible form fields as structured data: `label`, `input_name` or `id`, `type` (text, select, textarea, checkbox, file), `required`, `options` (for selects). Returns a list of dicts.
- **`apply.py` Phase 1 — DOM inspection**: `InspectFn` navigates to `apply_target.destination_url`. Checks for a login wall (email + password input pair with no visible job form) → raises `GenericCareerPageError(code="login_wall_detected")`. Otherwise runs `field_extractor.extract_form_fields(page)`.
- **Phase 2 — AI field mapping**: calls the LLM (via existing `groq_api_key` / `openai_api_key` settings) with a structured prompt: given the extracted field list and the available answer keys from the answer store, return a JSON `{input_name: answer_key}` mapping. Uses the same model as `groq_model` setting. The prompt explicitly asks the LLM to only map fields it is confident about — uncertain fields are left unmapped (creating `ensure_question_task` entries for human review).
- **Phase 3 — form fill**: for each mapped field, `resolve_questions` is called with synthetic `ApplyQuestion` objects whose `key` is the mapped answer key. Fields the LLM could not map generate question tasks for human input. Playwright fills the form and submits.
- **`blockers.py`**: `GenericCareerPageError`. Codes: `login_wall_detected`, `no_form_found`, `submit_failed`, `captcha_required`, `selector_missing`.
- Credential support: the generic driver checks `metadata["credential_policy"]` — if `tenant_required` or `optional` and an application account exists, credentials are passed. Default is `not_needed`.

**Patterns to follow:**
- LinkedIn driver lifecycle for the overall shape.
- `backend/app/integrations/openai/job_relevance.py` for the LLM call pattern (existing Groq/OpenAI wrapper).

**Test scenarios:**
- Happy path: `field_extractor.extract_form_fields` returns a list of field dicts from a mock Playwright page with a simple form.
- Happy path: AI field mapping returns a valid `{input_name: answer_key}` JSON from a stub LLM call; `execute_generic_career_page_run` proceeds to form fill.
- Happy path: fields the LLM cannot map produce `ensure_question_task` entries; `run.status == "blocked_missing_answer"`.
- Error path: a login wall is detected → `run.status == "action_needed"` with `code == "login_wall_detected"`.
- Error path: no form found on the page → `run.status == "action_needed"` with `code == "no_form_found"`.
- Error path: `_default_inspect` raises `runner_not_configured`.
- Edge case: a page with multiple forms — the extractor targets the first form that contains a submit button and at least one text input.

**Verification:**
- `execute_generic_career_page_run` follows the same event lifecycle as other drivers. The field extractor returns structured data from a mock page. The AI mapping integration test (with a stub LLM) produces the correct synthetic question list. Login walls surface as `action_needed` rather than silent failures.

---

- [ ] **Unit 7: Wire credential lookup into browser driver dispatch**

**Goal:** Ensure that browser drivers for iCIMS, Jobvite, and optionally Workday receive the decrypted credential at dispatch time — not inside the integration module — keeping the integration layer free of SQLAlchemy dependencies.

**Requirements:** R15-R20

**Dependencies:** Units 1-5

**Files:**
- Modify: `backend/app/domains/applications/service.py`
- Test: `backend/tests/domains/test_application_service.py` (extend)

**Approach:**
- In `execute_application_run`, after `ensure_target_ready` succeeds and `resolve_driver` returns a browser driver key, look up the application account and call `decrypt_secret` before invoking the driver.
- Pass the resulting `credential: str | None` as a keyword argument to `execute_icims_application_run`, `execute_jobvite_application_run`, `execute_workday_application_run`. If no account exists and the platform policy is `optional`, `credential=None` is passed. If policy is `tenant_required` and account is missing, `ensure_target_ready` already raised before reaching this point.
- The decrypted credential must not be logged. Service code passes it directly to the driver and then the driver passes it to `submit_flow`. Neither the credential value nor any derivative appears in `_log_event` calls.
- `decrypt_secret` is only called once per run, immediately before the driver invocation, not cached.

**Patterns to follow:**
- `backend/app/domains/application_accounts/service.py` `decrypt_secret` and `find_application_account_for_target`.

**Test scenarios:**
- Happy path: `execute_application_run` for an `icims_apply` target with a stored account calls `execute_icims_application_run` with a non-None `credential`.
- Happy path: `execute_application_run` for a `jobvite_apply` target with no account calls `execute_jobvite_application_run` with `credential=None`.
- Error path: the credential value must not appear in the `ApplicationEvent.payload` column — verified by checking that `redact_payload` or explicit exclusion keeps it out of all event dicts.
- Integration: end-to-end test with a stub `inspect_flow` and `submit_flow` confirms the credential flows from the encrypted database record through `decrypt_secret` to the stub submit function without appearing in any logged event.

**Verification:**
- Credential lookup and decryption happens exactly once per run in the service layer. No plaintext credential appears in any `ApplicationEvent.payload`. All browser driver dispatch paths receive the credential in the same consistent way.

---

- [ ] **Unit 8: Surface browser driver readiness in jobs list and portal**

**Goal:** Extend the jobs list and job detail API responses to surface platform-specific readiness reasons for browser targets (missing account, login failed, platform changed, etc.) so the user can act before triggering a run.

**Requirements:** R27-R30

**Dependencies:** Units 1-2

**Files:**
- Modify: `backend/app/domains/jobs/routes.py`
- Modify: `frontend/src/routes/jobs.tsx`
- Modify: `frontend/src/routes/job-detail.tsx`
- Test: `backend/tests/domains/test_portal_list_routes.py` (extend)

**Approach:**
- The jobs list route already has some status display. Extend the `ApplyTarget` serialization to include `platform_family`, `compatibility_state`, `credential_status`, and `readiness_reason` fields — populated from `resolve_target_readiness` called at serialization time (or pre-computed and cached on the `ApplyTarget.metadata_json`).
- Frontend: extend the status badge logic in `jobs.tsx` to handle `missing_application_account`, `login_failed`, `mfa_required`, and `platform_changed` with appropriate copy and a link to the Application Accounts tab on the Profile screen.
- `job-detail.tsx` already shows `missing_application_account` — extend to cover the new states from browser drivers.

**Patterns to follow:**
- Existing `job-detail.tsx` `missing_application_account` handling as the pattern for other states.
- The `TargetReadiness` dataclass in `application_accounts/service.py` as the source of truth for status vocabulary.

**Test scenarios:**
- Happy path: a job with a Workday target and no application account shows `missing_application_account` readiness state in the API response.
- Happy path: a job with an iCIMS target whose `credential_status == "login_failed"` shows `login_failed` readiness state.
- Integration: the portal list route returns readiness metadata without triggering a browser session.

**Verification:**
- The jobs list and job detail surface actionable readiness states for all browser-driver platforms. The user can navigate from a `login_failed` badge directly to the Application Accounts tab.

## System-Wide Impact

- **Interaction graph:** `service.execute_application_run` now routes to five browser driver families instead of one. `driver_registry.resolve_driver` is the single dispatch gate — any new platform adds one entry there. `ensure_target_ready` remains the credential/readiness gate before dispatch in all paths.
- **Error propagation:** Browser driver errors (`WorkdayAutomationError`, `iCIMSAutomationError`, etc.) must be caught in `service.py` and translated to `ApplicationRun.status` via `classify_*_exception`. They must not propagate as HTTP 500s. The credential parameter must not appear in any exception message or traceback logged to the event table.
- **State lifecycle risks:** `ApplicationAccount.credential_status` is updated after login success/failure. Concurrent runs for the same account+platform+tenant are not guarded — if the system is extended to run multiple jobs in parallel, a lock or soft-lock on the application account will be needed. For now (single-user, sequential runs) this is acceptable.
- **API surface parity:** `resolve_target_readiness` is called from both the trigger route and (in Unit 8) the jobs list route. Both must use the same readiness vocabulary — `missing_application_account`, `login_failed`, `mfa_required`, `platform_changed`, `ready`, `platform_not_supported`, `manual_only`.
- **Integration coverage:** Cross-layer tests should cover the path: resolved platform family → application account lookup → credential decryption → driver dispatch → stub submit → event log. These tests are defined per-unit above and should not mock `decrypt_secret` — they should use a real Fernet-encrypted test credential.
- **Unchanged invariants:** The system still applies at most once per canonical job. `ensure_target_ready` still blocks unready targets before any browser session starts. The LinkedIn driver is not modified. Direct-API platforms are not affected.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Playwright browser automation is fragile against DOM changes | Each driver uses `_default_inspect`/`_default_submit` stubs so tests pass without Playwright; `selector_missing` / `platform_changed` blocker codes surface regressions without crashing the run |
| Decrypted credentials leaking into logs or event payloads | `redact_payload` is applied to all submission payloads; service layer explicitly excludes the credential parameter from all `_log_event` calls; verified by test scenario in Unit 7 |
| Generic career page AI mapping hallucinating wrong field mappings | LLM is instructed to only map fields it is confident about; unmapped fields become question tasks for human review; the worst outcome is a blocked run, not a wrong submission |
| iCIMS account lockout from repeated failed login attempts | `record_login_failure` sets `credential_status = "login_failed"` after the first failure; `ensure_target_ready` blocks subsequent attempts until the user rotates the password; no auto-retry on login failure |
| Workday tenant-mode detection misclassifying login-gated tenants as conversational | Driver logs the detected mode in the event payload; if misclassified the run fails cleanly; user can inspect the artifact screenshot |
| Circular import fix breaking downstream imports | Unit 1 is the smallest possible change — only `ApplyTargetCandidate` moves, nothing else. The full test suite verifies no regressions before any other unit proceeds |
| Generic career page driver applied to sites with anti-bot measures | The driver does not attempt to defeat bot detection. CAPTCHA → `captcha_required` action_needed. Rate limiting → `action_needed`. No silent retry. |

## Phased Delivery

### Phase 1 (immediate)
- Unit 1: fix circular import
- Unit 2: extend driver registry

### Phase 2 (browser platform drivers)
- Unit 3: Workday
- Unit 4: iCIMS
- Unit 5: Jobvite
- Unit 7: credential wiring

### Phase 3 (generic + portal)
- Unit 6: generic career page driver
- Unit 8: surface readiness in jobs list

## Sources & References

- **Origin document:** [docs/plans/2026-04-09-002-feat-platform-matrix-and-application-accounts-plan.md](docs/plans/2026-04-09-002-feat-platform-matrix-and-application-accounts-plan.md)
- Related code: `backend/app/integrations/linkedin/apply.py`
- Related code: `backend/app/integrations/linkedin/blockers.py`
- Related code: `backend/app/domains/application_accounts/service.py`
- Related code: `backend/app/domains/applications/driver_registry.py`
- Related code: `backend/app/domains/sources/link_classification.py`
- External docs: `https://www.workday.com/en-be/products/conversational-ai/candidate-experience.html`
- External docs: `https://community.icims.com/articles/HowTo/Candidate-Guide-to-the-iCIMS-Talent-Platform`
- External docs: `https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html`
