---
title: "feat: Replace per-platform ATS drivers with unified AI browser agent"
type: feat
status: active
date: 2026-04-14
---

# feat: Replace per-platform ATS drivers with unified AI browser agent

## Overview

Replace the four separate Playwright ATS browser drivers (Workday, iCIMS, Jobvite, generic career page) with a single AI-driven browser agent using the `browser-use` Python library. The agent opens any job application URL, reads the page semantically using an LLM, fills form fields from the user's answer bank, and submits — without needing per-platform knowledge. The existing `InspectFn` / `SubmitFn` callable interface is preserved so the orchestration layer (`service.py`) requires minimal changes.

Direct-API drivers (Greenhouse, Lever, Ashby, SmartRecruiters) are kept as the **primary path** — fast, cheap, and reliable when the API works. The AI browser agent is added as an **automatic fallback**: if a direct-API run ends in a `TerminalApplyError`, `service.py` retries the same job via the AI browser agent on the `destination_url`. This gives full coverage without sacrificing API efficiency.

## Problem Frame

Per-platform drivers are brittle. Workday is a React multi-step wizard that changes structure. iCIMS requires tenant-specific login. Jobvite has inconsistent guest vs login flows. The generic driver uses regex field mapping via LLM which misses many fields. Each driver needs its own maintenance and can only handle one ATS. The fix: one AI browser agent that reads any page the way a human would and adapts dynamically.

## Requirements Trace

- R1. A single AI browser agent handles inspect and submit for all browser-driver platforms (Workday, iCIMS, Jobvite, generic career page)
- R2. The agent fills only fields where the user has answers in their answer bank — never hallucinating values
- R3. The `InspectFn` / `SubmitFn` callable interface is preserved — `service.py` dispatch logic is unchanged or minimally changed
- R4. Credentials (portal login) can be injected into the agent task prompt when present
- R5. Multi-step wizard forms (Workday) are handled by the agent navigating forward step by step
- R6. Failures (login wall, no form found, submit timeout) map to the existing `TerminalApplyError` / `RetryableApplyError` / blocker hierarchy
- R7. The `browser-use` library is added as an optional dependency alongside the existing `playwright` optional group
- R8. Direct-API drivers (Greenhouse, Lever, Ashby, SmartRecruiters) run first; if they end in a `TerminalApplyError`, `service.py` automatically retries via the AI browser agent using the job's `destination_url`
- R8b. The fallback is transparent — the same `ApplicationRun` record is reused; a `browser_fallback_attempted` event is logged before the retry
- R9. The agent runs synchronously inside Celery tasks (no async event loop conflict)

## Scope Boundaries

- Direct-API drivers are NOT replaced — they remain the primary path; the AI browser agent is fallback only
- The fallback only triggers on `TerminalApplyError` (e.g. Lever 403, expired posting) — not on `RetryableApplyError` (network hiccup) or `blocked_missing_answer`
- LinkedIn driver is NOT replaced — it has its own session/cookie requirements
- This plan does not add CAPTCHA-solving capability — CAPTCHA pages are treated as a `blocked_captcha` terminal error
- This plan does not change the question answer bank data model or `resolve_questions` logic
- Frontend changes are out of scope

## Context & Research

### Relevant Code and Patterns

- `backend/app/integrations/workday/apply.py` — current Workday driver; `InspectFn = Callable[[ApplyTarget, Path, str | None], WorkdayInspection]`, `SubmitFn = Callable[[ApplyTarget, Path, dict[str, Any], str | None], WorkdaySubmission]`
- `backend/app/integrations/icims/apply.py` — same shape with `credential: str` (not optional)
- `backend/app/integrations/jobvite/apply.py` — same shape, guest-first flow
- `backend/app/integrations/generic_career_page/apply.py` — same shape + LLM field mapping
- `backend/app/integrations/linkedin/apply.py` — reference driver shape; `InspectFn = Callable[[ApplyTarget, Path], LinkedInInspection]`
- `backend/app/integrations/browser_context.py` — `open_persistent_context(profile_dir, headless, timeout_ms)`, `find_submit_button(page)`
- `backend/app/integrations/linkedin/session_store.py` — `ensure_profile_dir(account_id, platform, settings)`
- `backend/app/integrations/linkedin/artifacts.py` — `persist_artifacts(run_id, artifacts_dict, settings)`
- `backend/app/domains/applications/service.py` — `execute_application_run()` dispatches by `driver.key`; each browser driver branch calls `find_application_account_for_target` + `decrypt_secret` then delegates to platform-specific `execute_*_run()`
- `backend/app/domains/applications/driver_registry.py` — `resolve_driver()` returns one of the driver constants; fallback already returns `GENERIC_CAREER_PAGE_DRIVER`
- `backend/app/domains/applications/retry_policy.py` — `TerminalApplyError`, `RetryableApplyError`, `classify_apply_exception()`
- `backend/app/domains/questions/matching.py` — `resolve_questions(session, account_id, questions) -> list[ResolvedQuestion]`; `ResolvedQuestion.answer_value` extracts the scalar answer
- `backend/app/config.py` — `groq_api_key`, `groq_model`, `openai_api_key`; `playwright_headless`, `playwright_timeout_ms`, `playwright_profile_dir`
- `backend/pyproject.toml` — `browser` optional group (`playwright>=1.40`)

### browser-use Library Key Facts

- `browser-use` is a Python library that wraps Playwright with an LLM agent loop. The agent is given a task string and takes browser actions (click, fill, navigate, scroll) until it decides the task is done.
- Installation: `pip install browser-use` — it installs Playwright as a dependency. Since Playwright is already in the optional `browser` group, browser-use should be added to the same group.
- The core API is **async**: `await agent.run()`. Running from sync Celery workers requires `asyncio.run(agent.run())` or a dedicated thread with its own event loop.
- You can pass a **custom Playwright browser** context to avoid browser-use launching its own. This is how we inject persistent profile dirs.
- The task string is plain text — user answers are injected as a structured JSON block within the prompt.
- browser-use returns an `AgentHistoryList` result; the final output/extracted data is available via `result.final_result()` and action history via `result.action_names()`.
- Supported LLM providers: OpenAI, Anthropic, and any LangChain-compatible provider (including Groq via `langchain-groq`).
- For structured output, a `output_model: type[BaseModel]` can be passed to `Agent`; the agent will attempt to populate it at the end of the run.
- Multi-step forms: the agent navigates forward naturally — it clicks "Next" buttons just like a human would.
- Failure modes: `MaxStepsReached` (configurable `max_steps`), navigation errors, and unhandled exceptions from Playwright all surface as Python exceptions from `agent.run()`.

### External References

- browser-use GitHub: `browser-use/browser-use` — Python async AI browser automation library
- LangChain ChatGroq: `langchain-groq` package for Groq-compatible LLM client

## Key Technical Decisions

- **Single shared agent driver, not per-platform subclasses**: One `AIBrowserDriver` module under `backend/app/integrations/ai_browser/` handles all browser-driver platforms. Per-platform routing in `service.py` collapses to a single branch.

- **Async agent, sync bridge via `asyncio.run()`**: browser-use is async-only. Celery workers are sync. We bridge with `asyncio.run(agent_coroutine)`. This is safe in Celery because each task runs in its own thread with no existing event loop. A helper `run_sync(coro)` in the agent module wraps this cleanly.

- **Two-phase design (inspect then submit) preserved**: The existing `InspectFn` / `SubmitFn` split is kept. Inspect runs the agent with a read-only task (extract form questions without filling). Submit runs the agent again with answers injected. This preserves the question-task / answer-resolution flow and the `blocked_missing_answer` status for unanswered required fields.

- **Answer injection via structured task prompt**: The user's resolved answers are serialized as a JSON object in the task string, e.g. `"Available answers: {"first_name": "Dan", "email": "dan@example.com", ...}"`. The agent is instructed to fill ONLY fields it can match to the available answers — do not guess or invent values.

- **Persistent profile dir passed as custom browser context**: We call `open_persistent_context(profile_dir, ...)` from `browser_context.py` to get a Playwright browser context, then pass it to the browser-use `Agent` via its `browser` parameter. This preserves session cookies (useful for login-gated portals).

- **Credential injection via task prompt**: When a credential (`email:password`) is available, it is included in the task string: `"If the page requires login, use email: X, password: Y"`. This avoids building a separate login automation step.

- **Blockers map to existing error types**: Agent failure → catch exception → classify into `TerminalApplyError` (login wall unsolvable, no form, CAPTCHA) or `RetryableApplyError` (timeout, network error). A new `AIBrowserBlocker` exception type carries a `code` and `message` for the event log.

- **`output_model` for inspect phase**: The inspect agent is given a Pydantic `InspectOutput` model with a `questions` list. This grounds the output and prevents hallucinated field names. Each extracted question maps to an `ApplyQuestion`.

- **LLM provider selection**: Use Groq (LangChain ChatGroq) when `groq_api_key` is set, otherwise fall back to OpenAI. This matches the existing pattern in `generic_career_page/apply.py`.

- **`max_steps` cap**: Set `max_steps=50` for inspect, `max_steps=100` for submit to prevent runaway agent loops.

- **Old per-platform drivers stay in the repo initially**: They are disconnected from `service.py` dispatch but kept for reference during rollout. Deletion is a follow-up cleanup.

## Open Questions

### Resolved During Planning

- **Can browser-use use an existing Playwright context?** Yes — the `Agent` constructor accepts a `browser` parameter (a `BrowserConfig` or an existing Playwright browser instance). We pass our persistent context.
- **Can Groq be used as the LLM?** Yes — via `langchain-groq` / `ChatGroq`. browser-use supports any LangChain chat model.
- **Does `asyncio.run()` work inside Celery?** Yes — Celery workers run in threads with no event loop. `asyncio.run()` creates a new event loop, runs the coroutine, and closes it. This is the standard pattern for sync→async bridging.
- **Where does `output_model` output land?** In `AgentHistoryList.final_result()` — a string that gets parsed into the Pydantic model.

### Deferred to Implementation

- Exact `max_steps` tuning — depends on real-world Workday/iCIMS wizard depth discovered during testing
- Whether `networkidle` or `domcontentloaded` is the right initial wait state when passing the context to browser-use — browser-use manages its own navigation waits
- Exact task prompt wording — iterate based on observed agent behavior
- Whether inspect and submit need separate LLM model configs or can share one setting

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

```
service.py: execute_application_run()
    → resolve_driver(target)
    │
    ├─ DIRECT_API_DRIVER (Greenhouse / Lever / Ashby / SmartRecruiters)
    │   → _execute_direct_api_application_run(...)
    │       success → return ApplyResult(status="submitted")
    │       RetryableApplyError / blocked_missing_answer → return as-is (no fallback)
    │       TerminalApplyError
    │           → log event "browser_fallback_attempted"
    │           → execute_ai_browser_run(session, account, job_id,
    │                                    destination_url=apply_target.destination_url)
    │           → return AI browser ApplyResult
    │
    ├─ AI_BROWSER_DRIVER (Workday / iCIMS / Jobvite / generic_career_page)
    │   → execute_ai_browser_run(session, account, job_id, credential)
    │
    └─ LINKEDIN_BROWSER_DRIVER → execute_linkedin_application_run(...)

ai_browser/apply.py: execute_ai_browser_run()
    ├── ensure_profile_dir(account_id, "ai_browser", settings)
    ├── open_persistent_context(profile_dir, ...) → pw, context
    ├── INSPECT PHASE
    │   build_inspect_task(destination_url, credential) → task_str
    │   Agent(task=task_str, llm=llm, browser=context, output_model=InspectOutput, max_steps=50)
    │   asyncio.run(agent.run()) → AgentHistoryList
    │   parse InspectOutput.questions → list[ApplyQuestion]
    │   → resolve_questions(session, account_id, questions)
    │   → if unresolved required: status=blocked_missing_answer, return
    ├── SUBMIT PHASE
    │   build_submit_task(destination_url, answers_by_key, credential) → task_str
    │   Agent(task=task_str, llm=llm, browser=context, max_steps=100)
    │   asyncio.run(agent.run())
    │   → status=submitted
    └── except → classify → TerminalApplyError or RetryableApplyError

driver_registry.py
    AI_BROWSER_DRIVER = ApplicationDriver(key="ai_browser", ...)
    resolve_driver() → AI_BROWSER_DRIVER for all browser-family platforms
                       (replaces individual workday/icims/jobvite/generic constants)
```

## Implementation Units

- [ ] **Unit 1: Add browser-use and langchain-groq dependencies**

**Goal:** Install `browser-use` and `langchain-groq` as optional dependencies alongside Playwright.

**Requirements:** R7, R9

**Dependencies:** None

**Files:**
- Modify: `backend/pyproject.toml`

**Approach:**
- Add `browser-use` and `langchain-groq` to the `[project.optional-dependencies]` `browser` group
- Do not add them to core `dependencies` — keep browser automation optional

**Test scenarios:**
- Happy path: `pip install -e ".[browser]"` installs without conflict

**Verification:**
- `import browser_use` and `import langchain_groq` succeed in the backend venv after install

---

- [ ] **Unit 2: AI browser agent module — core inspect and submit**

**Goal:** Create `backend/app/integrations/ai_browser/apply.py` with the full `execute_ai_browser_run()` function, inspect phase, submit phase, blocker classification, and event logging.

**Requirements:** R1, R2, R3, R4, R5, R6, R9

**Dependencies:** Unit 1

**Files:**
- Create: `backend/app/integrations/ai_browser/__init__.py`
- Create: `backend/app/integrations/ai_browser/apply.py`
- Create: `backend/app/integrations/ai_browser/blockers.py`
- Create: `backend/tests/integrations/test_ai_browser_apply.py`

**Approach:**
- `blockers.py`: define `AIBrowserBlocker(Exception)` with `code`, `step`, `message`, `artifacts` fields. Define `classify_ai_browser_exception(error) -> RetryDecision` mapping to `TerminalApplyError` (login wall, no form, captcha) or `RetryableApplyError` (timeout, network).
- `apply.py`:
  - `_build_llm(settings)` — returns `ChatGroq(model=settings.groq_model)` if `groq_api_key` set, else `ChatOpenAI(model=...)`.
  - `_build_inspect_task(url, credential)` — returns a task string instructing the agent to navigate to the URL, extract all visible form field labels and their types as a JSON list, and NOT fill any fields. If login is required and credential is provided, include it.
  - `_build_submit_task(url, answers_by_key, credential)` — returns a task string with answers serialized as JSON, instructing the agent to fill only matched fields and click submit. Include an explicit instruction: "Do not fill any field for which you do not have a provided answer."
  - `InspectOutput` Pydantic model: `questions: list[ExtractedField]` where `ExtractedField` has `label`, `field_type`, `required`, `options`.
  - `_run_inspect(apply_target, profile_dir, credential, settings)` — opens context, builds agent with `output_model=InspectOutput`, runs with `asyncio.run()`, parses result into `list[ApplyQuestion]`.
  - `_run_submit(apply_target, profile_dir, answers_by_key, credential, settings)` — opens context, builds agent with submit task, runs, captures screenshot artifact.
  - `execute_ai_browser_run(session, account, job_id, credential, settings)` — full orchestration: run inspect, resolve_questions, check for unresolved required, run submit, log all events. Pattern follows `execute_workday_application_run` in `workday/apply.py`.

**Patterns to follow:**
- `backend/app/integrations/workday/apply.py` — event logging, status transitions, artifact persistence
- `backend/app/integrations/generic_career_page/apply.py` — LLM client construction pattern (groq fallback)
- `backend/app/integrations/linkedin/artifacts.py` — `persist_artifacts(run_id, artifacts, settings)`

**Test scenarios:**
- Happy path: inspect returns 3 questions, all have answers, submit succeeds → `status=submitted`, 3 `answer_entry_ids`
- Happy path: inspect with credential triggers login instructions in task prompt
- Edge case: inspect returns 0 questions → `AIBrowserBlocker(code="no_form_found")` → `status=failed`
- Edge case: all required questions have answers but some optional ones don't → submit proceeds (only required gate blocks)
- Error path: required question has no answer → `status=blocked_missing_answer`, `QuestionTask` created
- Error path: agent raises timeout → classified as `RetryableApplyError` → `status=retry_scheduled`
- Error path: agent detects login wall, no credential → `AIBrowserBlocker(code="login_required")` → `status=failed`
- Integration: `execute_ai_browser_run` with stubbed inspect returning known questions → verify `resolve_questions` is called, events logged, session committed

**Verification:**
- Unit tests pass with mocked `asyncio.run` and stubbed agent output
- All event types (queued, questions_fetched, submitted / blocked / failed) are logged correctly

---

- [ ] **Unit 3: Connect AI browser driver to service.py dispatch**

**Goal:** Wire `AI_BROWSER_DRIVER` into `driver_registry.py` and replace the four per-platform browser dispatch branches in `service.py` with a single `ai_browser` branch.

**Requirements:** R3, R8

**Dependencies:** Unit 2

**Files:**
- Modify: `backend/app/domains/applications/driver_registry.py`
- Modify: `backend/app/domains/applications/service.py`
- Test: `backend/tests/domains/test_application_service.py`

**Approach:**
- In `driver_registry.py`: add `AI_BROWSER_DRIVER = ApplicationDriver(key="ai_browser", label="AI browser agent", driver_family="browser")`. In `resolve_driver()`, replace the individual `workday_browser`, `icims_browser`, `jobvite_browser`, `generic_career_page` returns with a single check: `if definition.driver_family == "browser" and definition.family != "linkedin": return AI_BROWSER_DRIVER`.
- In `service.py`: remove the four `if driver.key == "workday_browser"`, `icims_browser`, `jobvite_browser`, `generic_career_page` branches. Add one `if driver.key == "ai_browser"` branch that calls `execute_ai_browser_run(...)`. LinkedIn branch stays unchanged.
- Keep `WORKDAY_BROWSER_DRIVER`, `ICIMS_BROWSER_DRIVER`, `JOBVITE_BROWSER_DRIVER`, `GENERIC_CAREER_PAGE_DRIVER` constants in `driver_registry.py` (do not delete yet — they may be referenced in tests or future rollback).

**Patterns to follow:**
- Existing `driver.key == "linkedin_browser"` branch in `service.py`
- `find_application_account_for_target` + `decrypt_secret` pattern already in each browser branch

**Test scenarios:**
- Happy path: target_type `workday_apply` → `resolve_driver` returns `AI_BROWSER_DRIVER`
- Happy path: target_type `icims_apply` → `resolve_driver` returns `AI_BROWSER_DRIVER`
- Happy path: target_type `jobvite_apply` → `resolve_driver` returns `AI_BROWSER_DRIVER`
- Happy path: target_type `generic_career_page` → `resolve_driver` returns `AI_BROWSER_DRIVER`
- Unchanged: target_type `greenhouse_apply` → returns `DIRECT_API_DRIVER`
- Unchanged: target_type `linkedin_easy_apply` → returns `LINKEDIN_BROWSER_DRIVER`
- Integration: `execute_application_run` with a `workday_apply` target calls `execute_ai_browser_run` (not the old Workday function)

**Verification:**
- No existing test for direct-API platforms breaks
- LinkedIn dispatch is unaffected

---

- [ ] **Unit 4: Update platform_matrix.py — collapse browser driver credential policies**

**Goal:** Ensure `platform_matrix.py` credential policies for iCIMS and Jobvite are correct (`tenant_required`) and that the AI browser agent can receive credentials for any platform that needs them.

**Requirements:** R4

**Dependencies:** Unit 3

**Files:**
- Modify: `backend/app/domains/applications/platform_matrix.py`
- Test: (covered by existing `test_application_service.py` — credential injection path)

**Approach:**
- No structural changes needed to `platform_matrix.py` — credential policies are already correct (`optional` for Workday, `tenant_required` for iCIMS/Jobvite, `not_needed` for generic).
- Verify that `service.py`'s `ai_browser` branch uses `find_application_account_for_target` and passes credential regardless of platform (let the agent decide whether to use it based on what the page shows).
- If `credential_policy == "tenant_required"` and no credential is found, raise `TerminalApplyError` before even starting the agent (same guard that was in the old iCIMS driver).

**Test scenarios:**
- iCIMS target with no application account → `TerminalApplyError` before agent runs
- Workday target with no application account → credential is `None`, agent proceeds (policy is `optional`)

**Verification:**
- Credential guard logic is exercised in unit tests

---

- [ ] **Unit 5: AI browser fallback for direct-API terminal failures**

**Goal:** When a direct-API run (Greenhouse, Lever, Ashby, SmartRecruiters) ends in `TerminalApplyError`, automatically retry via the AI browser agent on the job's `destination_url`.

**Requirements:** R8, R8b

**Dependencies:** Unit 2, Unit 3

**Files:**
- Modify: `backend/app/domains/applications/service.py`
- Test: `backend/tests/domains/test_application_service.py`

**Approach:**
- In `_execute_direct_api_application_run()`: wrap the existing try/except. When a `TerminalApplyError` is caught, check if `apply_target.destination_url` is set and the driver is `DIRECT_API_DRIVER`. If so, log a `browser_fallback_attempted` event on the existing `run`, then call `execute_ai_browser_run(session, account, job_id=job.id, credential=None, destination_url=apply_target.destination_url)`.
- The AI browser run reuses the same `ApplicationRun` record — pass `run` into `execute_ai_browser_run` so it appends events rather than creating a new run.
- `execute_ai_browser_run` must accept an optional `destination_url` override (for the fallback path, the target type is still `greenhouse_apply` etc., but the URL comes from `apply_target.destination_url`).
- If the AI browser fallback also fails, return whatever status the browser run produced — do not mask the error.
- `RetryableApplyError` and `blocked_missing_answer` from the direct-API path do NOT trigger the fallback — only `TerminalApplyError` does.

**Test scenarios:**
- Happy path: Lever returns 403 (`TerminalApplyError`) → fallback to AI browser → AI browser succeeds → `status=submitted`, `browser_fallback_attempted` event in run history
- Edge case: Lever returns 403 → fallback → AI browser also fails → final status is AI browser's failure status (not re-raised Lever error)
- Edge case: Lever returns 503 (`RetryableApplyError`) → no fallback → `status=retry_scheduled`
- Edge case: no `destination_url` on apply_target → no fallback attempted, original `TerminalApplyError` status preserved
- Unchanged: Greenhouse happy path succeeds via API → no fallback triggered

**Verification:**
- `browser_fallback_attempted` event appears in event log when fallback fires
- Direct-API success path is unaffected (no extra function calls)

---

- [ ] **Unit 6: Remove old per-platform browser driver modules (cleanup)**

**Goal:** Delete the now-unused Workday, iCIMS, Jobvite, and generic career page driver modules and their blocker files.

**Requirements:** R1 (simplification)

**Dependencies:** Unit 3, Unit 5 (must be disconnected from dispatch first)

**Files:**
- Delete: `backend/app/integrations/workday/apply.py`
- Delete: `backend/app/integrations/workday/blockers.py`
- Delete: `backend/app/integrations/icims/apply.py`
- Delete: `backend/app/integrations/icims/blockers.py`
- Delete: `backend/app/integrations/jobvite/apply.py`
- Delete: `backend/app/integrations/jobvite/blockers.py`
- Delete: `backend/app/integrations/generic_career_page/apply.py`
- Delete: `backend/app/integrations/generic_career_page/blockers.py`
- Delete: `backend/app/integrations/generic_career_page/field_extractor.py` (if only used by old driver)
- Modify: `backend/app/integrations/browser_context.py` — keep `open_persistent_context` and `find_submit_button`; remove anything only used by deleted drivers

**Approach:**
- Grep for any remaining imports of the deleted modules before deleting
- Keep `browser_context.py` — it's still needed by the AI browser driver and LinkedIn
- Check if `__init__.py` files in the platform dirs need cleanup

**Test scenarios:**
- No import errors after deletion
- Existing tests for non-deleted integrations still pass

**Verification:**
- `grep -r "from app.integrations.workday" backend/` returns empty
- Test suite passes

## System-Wide Impact

- **Dispatch simplification:** `service.py` goes from 5 browser dispatch branches to 2 (LinkedIn + AI browser). Reduces maintenance surface.
- **Driver registry:** `resolve_driver()` is simplified — one check replaces four. Old driver constants remain defined but unused.
- **Error propagation:** All AI browser errors classify through the existing `classify_apply_exception()` path. No new status codes are introduced.
- **State lifecycle:** The `ApplicationRun` status machine is unchanged — `queued → questions_fetched → submitted / blocked_missing_answer / failed / retry_scheduled`. The AI agent driver uses the same transitions.
- **Credentials:** `find_application_account_for_target` + `decrypt_secret` pattern is preserved in the `ai_browser` service branch. The agent receives the decrypted string.
- **Answer bank:** `resolve_questions` and `ensure_question_task` are called identically — the AI agent's extracted questions go through the same fingerprint / alias / answer lookup as before.
- **Playwright sessions:** Persistent profile dirs are still created via `ensure_profile_dir`. Session cookies persist across runs for the same account + platform.
- **Unchanged invariants:** Greenhouse / Lever / Ashby / SmartRecruiters direct-API paths run first as before. The only change is a fallback leg added after `TerminalApplyError`. LinkedIn browser path is completely unaffected.
- **Fallback event trail:** A single `ApplicationRun` accumulates events from both the direct-API attempt and the browser fallback, giving full traceability.
- **Integration coverage:** The AI agent's inspect → resolve → submit flow must be tested with a stubbed `asyncio.run` that returns a known `AgentHistoryList` — real browser tests are deferred to manual / E2E testing.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| browser-use API changes between versions — it is a fast-moving library | Pin to a specific version in pyproject.toml; review changelog before upgrading |
| Async bridge (`asyncio.run`) may conflict with future async Celery migration | Isolate async in a `run_sync()` helper so the bridge is one file to update |
| Agent hallucinates field values when answer is absent | Explicit task prompt instruction: "Do not fill any field for which you do not have a provided answer"; `output_model` for inspect grounds question extraction |
| Multi-step wizard (Workday) causes agent to exceed `max_steps` | Tune `max_steps` upward; classify `MaxStepsReached` as `RetryableApplyError` so it can be retried |
| Login-gated portals (iCIMS) fail silently if credential is wrong | Agent detects continued login wall after login attempt; raise `AIBrowserBlocker(code="login_failed")` as `TerminalApplyError` |
| browser-use requires Playwright to be installed separately | It ships Playwright as a dep — should not conflict with our existing `playwright>=1.40` pin; verify on install |
| Cost: multiple LLM calls per application run | Groq is cheap (~$0.01–0.05/run estimated). Direct-API runs avoid the cost entirely; browser agent only fires as needed. Monitor via event logs. |
| Fallback adds latency to already-failed runs | Acceptable — the direct-API run already failed terminally; user was getting no result anyway |
| Direct-API terminal errors that should stay terminal (e.g. job closed) still trigger expensive fallback | Log `browser_fallback_attempted` and track rate; add a denylist of terminal codes to skip fallback if this becomes noise |
| LangChain added as a transitive dependency | `langchain-groq` brings langchain-core; keep in optional `browser` group to avoid polluting the core install |

## Documentation / Operational Notes

- Add `browser-use` and `langchain-groq` to the `[browser]` optional dep group install instructions in any setup docs
- The `ai_browser_model` setting can be added to `config.py` when per-driver model control is needed (deferred)
- Monitor `questions_fetched` event `question_count` in logs — if consistently 0, the inspect task prompt needs tuning
- Artifact screenshots from the agent are persisted via `persist_artifacts` for debugging failed runs

## Sources & References

- Related plan: [2026-04-10-001-feat-real-playwright-browser-drivers-plan.md](docs/plans/2026-04-10-001-feat-real-playwright-browser-drivers-plan.md)
- browser-use library: https://github.com/browser-use/browser-use
- Reference driver: `backend/app/integrations/workday/apply.py`
- Orchestration: `backend/app/domains/applications/service.py`
- Driver registry: `backend/app/domains/applications/driver_registry.py`
