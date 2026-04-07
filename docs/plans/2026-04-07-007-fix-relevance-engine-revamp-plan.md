---
title: fix: Revamp relevance engine — prompt-driven gates with correct family semantics
type: fix
status: active
date: 2026-04-07
---

# fix: Revamp relevance engine — prompt-driven gates with correct family semantics

## Overview

Both Phase 1 (AI title screening) and Phase 2 (AI full relevance) have defects that cause obviously valid SWE jobs to be rejected, stuck in repair loops, or over-classified as `review`. This plan fixes both phases by enriching the AI context with role-family and level-band semantics derived from the user profile, removing unnecessary verify/repair loops, and fixing structural brittleness in the consistency guards. The gate architecture is also made explicitly extensible for future gates (country, focus) without building them yet.

## Problem Frame

### Phase 1 Defects

**Root cause: the role prompt is too sparse.** A bare string like `"SWE new grad"` does not communicate role-family context well enough. LLaMA 4 Scout on Groq must infer that "Backend Engineer", "Full-Stack Developer", "Junior Software Developer", "Graduate Software Developer", and "Associate SWE" are all the same family. When it gets this wrong, the repair and verify loops can also fail, landing the job in `system_fallback` (retries as `pending`) or incorrectly rejecting it.

**The `_verify_reject_with_ai` third-pass call is unnecessary.** When a reject passes `_title_screening_inconsistent` but fails `_title_screening_safe_reject`, the code calls the AI a third time to verify the reject. `_title_screening_safe_reject` already requires very strong evidence (`different_family` + `clear_family_mismatch` + `material_scope_change` + `moderate/strong` contradiction). If that bar isn't met, the right response is to override to `pass`, not to call the AI again.

**The `_title_screening_inconsistent` guard treats any `None` structured field as inconsistent.** A missing or unrecognized value in any one field triggers the full repair loop even when the decision itself is correct.

### Phase 2 Defects

**Same sparse-prompt problem.** The bare `profile.prompt` is sent to Phase 2 without role-family enrichment. Jobs that correctly passed Phase 1 still receive `review` instead of `match` because the classifier gets the same thin context.

**`matched_titles` is always `[job.title]` — the field is effectively unused.** The prompt passes `matched_titles` as context but it is always just the title itself. If the catalog were used here, it would give the classifier strong evidence the job is in-family. Currently the field provides no signal.

**Phase 2 uses `{"type": "json_object"}` instead of `json_schema`.** Phase 1 uses `json_schema` response format for structured output. Phase 2 uses free-form `json_object`, which is less reliable for consistent structured fields and contributes to the `_relevance_payload_inconsistent` firing rate.

**`_relevance_payload_inconsistent` has the same `None`-triggers-repair brittleness.** One malformed field in the response sends the entire batch item into `_repair_with_ai`. When the repair also fails (`ValueError("repair_response_inconsistent")`), the exception propagates up to the batch handler and the whole job falls to `_fallback_review` with `review`.

**`_repair_with_ai` propagates `ValueError` on inconsistency.** In `_classify_batch_with_ai` the repair is called inside the item loop; an exception here causes an individual item to fall to `_default_review_from_missing_batch_result`. In `_classify_with_ai` (single-job path) the repair failure propagates up to the retry/fallback wrapper. Both paths result in unnecessary `review` outcomes.

**What correct behavior looks like:**
- Profile prompt: `"SWE new grad"`
- Phase 1 PASS: Backend Engineer – New Grad, Entry Level Full-Stack Developer, Junior Software Developer, Software Developer – New Graduate, Associate Software Engineer (AI Agent Developer), Graduate SWE
- Phase 1 REJECT: Hardware Engineer, Data Scientist, Product Manager, Staff ML Engineer
- Phase 2 MATCH (for all Phase 1 passes with no contradicting description): direct `match`, not `review`

## Requirements Trace

- R1. Phase 1 must pass all in-family SWE title variants (Backend, Fullstack, Associate, Graduate, Junior) for a "SWE new grad" profile
- R2. Phase 1 must reject clearly out-of-family titles (Hardware Engineer, Data Scientist, PM)
- R3. Phase 2 must prefer `match` over `review` for jobs that passed Phase 1 with no contradicting description context
- R4. Phase 2 must correctly classify role family and seniority for in-family SWE roles
- R5. The gate architecture must be extensible for future gates (country, focus) without restructuring the pipeline
- R6. Fallback behavior on provider failure must still pass (Phase 1) or `review` (Phase 2) — not silently reject
- R7. `pending` must remain valid for transient failures
- R8. Tests must cover the specific known-failing title examples for both phases

## Scope Boundaries

- This plan fixes Phase 1 and Phase 2 accuracy, prompt enrichment, and structural brittleness.
- Future gates (country, focus area) are NOT built here — only the extensibility slot is made explicit.
- No DB schema changes.
- No new AI models or providers.
- The `relevance_policy.py` `build_decision_policy` / `derive_profile_hints` contract stays unchanged in shape.
- Application submission, answer memory, and job deduplication are not touched.

## Context & Research

### Relevant Code and Patterns

- Phase 1 implementation: `backend/app/integrations/openai/job_title_screening.py` — `classify_job_titles` → `_classify_batch_with_ai` → optional `_repair_item_with_ai` / `_verify_reject_with_ai`
- Phase 2 implementation: `backend/app/integrations/openai/job_relevance.py` — `classify_job_relevance_batch` → `_classify_batch_with_ai` → optional `_repair_with_ai`
- Service layer: `backend/app/domains/jobs/relevance.py` — `screen_candidate_titles`, `evaluate_candidate_relevance`, `evaluate_job_relevance`
- Policy/hints: `backend/app/domains/jobs/relevance_policy.py` — `build_decision_policy`, `derive_profile_hints`
- Task processor: `backend/app/tasks/job_relevance.py` — `_process_title_screening_tasks`, `_process_full_relevance_tasks`
- Existing tests: `backend/tests/integrations/test_job_title_screening_client.py`, `backend/tests/integrations/test_job_relevance_client.py`, `backend/tests/tasks/test_job_relevance_task.py`, `backend/tests/domains/test_job_relevance_service.py`

### Key Existing Patterns

- `derived_profile_hints` (from `derive_profile_hints`) already computes `target_level_band` (early_career/mid/senior_plus) and `prompt_mentions_entry_level`. This is the right signal to weave into system prompts.
- `_title_screening_safe_reject` already requires very strong evidence for a reject. The verify loop is redundant.
- Phase 1 already uses `json_schema` response format — Phase 2 should match this.
- The `ScreenedTitle` class in `relevance.py` is the natural extensibility point for future gates.

## Key Technical Decisions

- **Fix both phases by enriching the system prompt with derived profile context.** The `derived_profile_hints` already computed by `derive_profile_hints` give us `target_level_band`. Add a role-family/level description to the system prompt text so the AI knows what "SWE new grad" implies: "software engineering discipline, early-career level — pass any title in that family regardless of exact wording, using level-band hint to handle seniority."

- **Remove `_verify_reject_with_ai` from Phase 1.** When `_title_screening_safe_reject` returns `False` for a reject decision, override to `pass` directly. No third AI call.

- **Fix Phase 2 to use `json_schema` response format.** Phase 1 already uses `_json_schema_response_format()` successfully with Groq LLaMA 4 Scout (comment in that helper notes "best-effort json_schema but not strict constrained decoding"). Switching Phase 2 from `{"type": "json_object"}` to `json_schema` with `strict: false` gives the model field-level schema hints, directly reducing the rate of missing/misspelled fields that trigger `_relevance_payload_inconsistent`. The `_json_schema_response_format` helper from `job_title_screening.py` should be extracted to a shared location and reused — do not duplicate it. Three call sites in `job_relevance.py` (lines ~240, ~324, ~439) need updating. Schema must use only `type`, `properties`, `required`, `additionalProperties`, and `enum` — no `$ref` or `allOf`.

- **Fix `_repair_with_ai` (Phase 2) to not propagate `ValueError`.** When the repair response is itself inconsistent, fall back to a safe default rather than raising. For Phase 2, a repaired-but-still-inconsistent result should fall to `review` (not raise), which is already the intent.

- **Populate `matched_titles` from `profile.generated_titles` in Phase 2.** The `matched_titles` field is currently always `[job.title]`. Pass `profile.generated_titles` (or a subset of the closest matches) as the catalog context for Phase 2, giving the classifier strong evidence the job is in-family.

- **Make the gate abstraction explicit with `TitleGateResult` (renamed from `ScreenedTitle`).** Add a `gate_name: str` field (default `"title"`). Future gates return the same shape and plug into the same early-exit chain in `evaluate_candidate_relevance` / `evaluate_job_relevance`.

- **Do not remove the `_repair_item_with_ai` call from Phase 1.** The single-call repair for inconsistent structured fields is still useful. Only the verify loop (third call for rejects) is removed.

## Open Questions

### Resolved During Planning

- **Should we change the AI model?** No — model selection is a config change independent of this plan.
- **Should Phase 1 use a static title catalog (plan 005 approach) instead of AI?** No — AI screening is the right mechanism. The bug is prompt quality, not mechanism choice.
- **Should `_verify_reject_with_ai` stay?** No — remove it. `_title_screening_safe_reject` is already the safety bar.
- **Should Phase 2 use `json_schema` format?** Yes — align with Phase 1.

### Deferred to Implementation

- Exact wording of the enriched system prompt for both phases — implementer should test against known-failing examples and tune.
- Whether `build_title_screening_system_prompt` helper lives in `relevance_policy.py` or inline in the integration files — choose based on test ergonomics.
- Whether `generated_titles` should be trimmed before being passed as `matched_titles` context in Phase 2 (e.g., top N titles by normalized similarity to the job title) — start with passing the full list and trim if token budget is a concern.

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

**Phase 1 — proposed flow:**

```
classify_job_titles(role_prompt, titles, derived_profile_hints)
  → system_prompt = base_instructions + role_family_context(role_prompt, derived_profile_hints)
       "User wants: software engineering, early-career level.
        Pass any title in the software engineering family at new-grad/junior/associate level.
        Reject only titles that name a clearly different discipline."
  → AI call with enriched system prompt
  → if inconsistent field: _repair_item_with_ai  (keep, 2nd call)
  → if reject but not safe_reject: override to pass  (NO 3rd call)
```

**Phase 2 — proposed flow:**

```
classify_job_relevance_batch(profile, jobs, derived_profile_hints)
  → system_prompt = base_instructions + role_family_context(profile.prompt, derived_profile_hints)
  → user message includes matched_titles = profile.generated_titles (catalog context)
  → response_format = json_schema  (structured, not free-form)
  → if inconsistent fields: _repair_with_ai  (keep, 2nd call)
  → if repair also inconsistent: fallback to review  (no propagating ValueError)
```

**Gate extensibility:**

```
evaluate_candidate_relevance(profile, candidate):
  # Phase 1 gate — always runs
  title_result = run_title_gate(profile, candidate.title)   # returns TitleGateResult(gate_name="title")
  if title_result.decision == "reject": return title_screen_reject_result(...)
  if title_result.failure_cause: return title_screen_pending_result(...)

  # Future gates slot in here:
  # country_result = run_country_gate(profile, candidate.location)
  # if country_result.decision == "reject": return gate_reject_result(country_result)

  # Phase 2 — runs only if all gates pass
  return classify_job_relevance(...)
```

## Implementation Units

- [ ] **Unit 1: Enrich Phase 1 system prompt with role-family and level-band context; remove `_verify_reject_with_ai`**

**Goal:** Make Phase 1 correctly classify in-family SWE title variants and remove the third-AI-call verify loop.

**Requirements:** R1, R2, R4, R6

**Dependencies:** None

**Files:**
- Modify: `backend/app/integrations/openai/job_title_screening.py`
- Modify: `backend/app/domains/jobs/relevance_policy.py`
- Test: `backend/tests/integrations/test_job_title_screening_client.py`
- Test: `backend/tests/domains/test_relevance_policy.py`

**Approach:**
- Add a helper (in `relevance_policy.py` or locally) that builds a role-context string from `role_prompt` + `derived_profile_hints`. For `early_career` band: "The user is targeting **[role_prompt]** roles at early-career level (new grad, junior, associate, graduate, entry level). Pass any title that represents [role_prompt]-discipline work at a compatible level. Do not reject because of level wording variants. Reject only titles that clearly name a different discipline."
- Prepend this context block to the existing `_classify_batch_with_ai` system prompt.
- Remove the `_verify_reject_with_ai` function and its call site. Where it was called (reject that fails `_title_screening_safe_reject`), replace with direct override to `pass`.
- Keep `_repair_item_with_ai` for inconsistent structured fields.

**Patterns to follow:** Existing system prompt structure in `_classify_batch_with_ai`; `derive_profile_hints` output shape

**Test scenarios:**
- Happy path: `classify_job_titles("SWE new grad", ["Backend Engineer – New Grad"], ...)` with fake client returning `pass` → result is `pass`
- Happy path: `classify_job_titles("SWE new grad", ["Hardware Engineer"], ...)` with fake client returning consistent `reject` (different_family + clear_family_mismatch + strong) → result is `reject`
- Edge case: `classify_job_titles("SWE new grad", ["Associate Software Engineer (AI Agent Developer)"], ...)` with fake `pass` → returns `pass` without repair
- Error path: reject that fails `_title_screening_safe_reject` → overridden to `pass`, no third AI call, no `_verify_reject_with_ai` invocation
- Integration: enriched system prompt includes level-band text when `target_level_band == "early_career"`
- Regression: no-profile path still returns all `pass` via `system_fallback`
- Regression: transient AI failure still returns `system_fallback` items with `pass` decision

**Verification:**
- No `_verify_reject_with_ai` function exists anywhere after the change
- Parametrized test covering all 6 known-failing titles passes (see Unit 3)
- Existing test suite remains green

---

- [ ] **Unit 2: Fix Phase 2 — enrich prompt, use `json_schema`, populate `matched_titles`, fix `_repair_with_ai` propagation**

**Goal:** Make Phase 2 correctly prefer `match` for in-family roles, reduce repair-loop frequency with structured output, and prevent repair failures from silently pushing jobs to `review`.

**Requirements:** R3, R4, R6

**Dependencies:** Unit 1 (shared `relevance_policy.py` helper from Unit 1 is reused here)

**Files:**
- Modify: `backend/app/integrations/openai/job_relevance.py`
- Modify: `backend/app/domains/jobs/relevance.py` (populate `matched_titles` from `profile.generated_titles`)
- Test: `backend/tests/integrations/test_job_relevance_client.py`
- Test: `backend/tests/domains/test_job_relevance_service.py`

**Approach:**
- Reuse the role-family context builder from Unit 1 to enrich the Phase 2 system prompt with role-family and level-band text.
- Switch Phase 2 `response_format` from `{"type": "json_object"}` to `json_schema` (matching Phase 1's approach). Define a `JOB_RELEVANCE_SCHEMA` constant with the expected response fields: `decision`, `score`, `summary`, `matched_signals`, `concerns`, `decision_rationale_type`, `role_family_alignment`, `seniority_alignment`, `modifier_impact`, `contradiction_strength`.
- In `build_batch_request_for_job` (in `relevance.py`) and in `evaluate_candidate_relevance` / `evaluate_job_relevance`, populate `matched_titles` from `profile.generated_titles` instead of just `[job.title]`.
- Fix `_repair_with_ai` to catch its own `ValueError("repair_response_inconsistent")` and return a safe `review` payload instead of raising. The caller in `_classify_batch_with_ai` should not need a try/except for the repair.
- Fix `_classify_with_ai` (single-job path) similarly: if repair raises, fall back to `_fallback_review` rather than propagating.

**Patterns to follow:**
- Phase 1's `TITLE_SCREENING_SCHEMA` constant and `_json_schema_response_format` helper — replicate the pattern for Phase 2
- `build_batch_request_for_job` in `relevance.py` — this is where `matched_titles` is currently set to `[job.title]`

**Test scenarios:**
- Happy path: Phase 2 with fake AI returning `match` for a Backend Engineer who passed Phase 1 → result is `match`
- Happy path: Phase 2 with `profile.generated_titles = ["Software Engineer I", "Junior SWE"]` → `matched_titles` in prompt contains those titles
- Edge case: Phase 2 repair called and repair response is also inconsistent → falls to `review` (no `ValueError` raised)
- Error path: `json_schema` response format used in API call (verifiable via captured kwargs in fake client)
- Regression: Phase 2 `review` decision still returned when description snippet contains contradicting context
- Regression: Phase 2 `reject` still returned when full context shows clearly out-of-family role

**Verification:**
- Phase 2 no longer uses `{"type": "json_object"}` response format — uses `json_schema`
- `matched_titles` in the Phase 2 request is populated from `profile.generated_titles` when available
- Repair failure in Phase 2 produces `review` (not raised exception)
- Existing test suite green

---

- [ ] **Unit 3: Rename `ScreenedTitle` → `TitleGateResult`; add `gate_name` field**

**Goal:** Make the gate abstraction explicit so future gates plug into the same pattern without restructuring the pipeline.

**Requirements:** R5

**Dependencies:** Units 1 and 2 (same files touched)

**Files:**
- Modify: `backend/app/domains/jobs/relevance.py`
- Modify: `backend/app/tasks/job_relevance.py`
- Test: `backend/tests/domains/test_job_relevance_service.py`
- Test: `backend/tests/tasks/test_job_relevance_task.py`

**Approach:**
- Rename `ScreenedTitle` → `TitleGateResult` everywhere. Add `gate_name: str` slot defaulting to `"title"`.
- Add a comment block in `evaluate_candidate_relevance` and `evaluate_job_relevance` (in `relevance.py`) marking the extensibility point: "future gates (country, focus) plug in here as additional early-exits before Phase 2."
- Pure refactor — no behavior change.

**Patterns to follow:** Existing `ScreenedTitle.__slots__` pattern

**Test scenarios:**
- Happy path: `TitleGateResult` with `gate_name="title"` returned from `screen_candidate_titles`
- Regression: all existing tests updated to use `TitleGateResult` and pass

**Verification:**
- No `ScreenedTitle` references remain in the backend
- All tests pass after rename

---

- [ ] **Unit 4: Add parametrized regression tests for known-failing title examples**

**Goal:** Lock in the specific failing examples so future regressions are caught immediately.

**Requirements:** R1, R2, R3, R8

**Dependencies:** Units 1 and 2

**Files:**
- Modify: `backend/tests/integrations/test_job_title_screening_client.py`
- Modify: `backend/tests/integrations/test_job_relevance_client.py`
- Modify: `backend/tests/domains/test_job_relevance_service.py`
- Modify: `backend/tests/tasks/test_job_relevance_task.py`

**Approach:**
- In `test_job_title_screening_client.py`: add parametrized tests for each known-failing title using `_FakeClient` responses. Test both the `pass` cases and the `reject` case (Hardware Engineer).
- In `test_job_relevance_service.py`: add tests verifying that "Hardware Engineer" rejected at Phase 1 never reaches Phase 2, and "Backend Engineer – New Grad" passed at Phase 1 does reach Phase 2.
- In `test_job_relevance_client.py`: add a test verifying Phase 2 returns `match` (not `review`) for in-family SWE jobs with consistent AI response.

**Patterns to follow:** Existing `_FakeClient` / `monkeypatch.setattr` patterns in the respective test files

**Test scenarios:**
- Phase 1 PASS: "Backend Engineer – New Grad" → fake `pass` response → `pass`
- Phase 1 PASS: "Entry Level Full-Stack Developer" → fake `pass` response → `pass`
- Phase 1 PASS: "Junior Software Developer - London - Bournemouth" → fake `pass` response → `pass`
- Phase 1 PASS: "Software Developer – New Graduate" → fake `pass` response → `pass`
- Phase 1 PASS: "Associate Software Engineer (AI Agent Developer)" → fake `pass` response → `pass`
- Phase 1 REJECT: "Hardware Engineer" → fake `reject` with `different_family` / `clear_family_mismatch` / `strong` → `reject`
- Integration: "Hardware Engineer" rejected at Phase 1 → `evaluate_candidate_relevance` returns `reject` without calling Phase 2
- Integration: "Backend Engineer – New Grad" passed at Phase 1 → `evaluate_candidate_relevance` calls Phase 2
- Phase 2: in-family SWE job with consistent AI `match` response → result is `match` (not `review`)

**Verification:**
- `pytest backend/tests/integrations/ backend/tests/domains/ backend/tests/tasks/` all green
- Each known-failing title has at least one test case

## System-Wide Impact

- **Interaction graph:** `classify_job_titles` and `classify_job_relevance_batch` are the two AI call sites. Both are called from `relevance.py`, which is called from `job_relevance.py` task processor. No external API contracts change.
- **Error propagation:** Removing `_verify_reject_with_ai` removes one failure surface. Fixing `_repair_with_ai` to not propagate `ValueError` removes another. The existing fallback-to-pass (Phase 1) and fallback-to-review (Phase 2) contracts are preserved.
- **State lifecycle risks:** No DB schema changes. Jobs already stored with incorrect Phase 1 rejects may need rescoring — the existing `rescore_account_jobs_now` machinery handles this. Run it after shipping.
- **API surface parity:** `routes.py` job list/detail API is unchanged. No new `relevance_source` values introduced.
- **Integration coverage:** The `_process_title_screening_tasks` and `_process_full_relevance_tasks` batch paths in `job_relevance.py` call the same functions — the enriched prompt fixes benefit these paths automatically.
- **Unchanged invariants:** `pending` state, task queue phases, cache invalidation in `cached_relevance_for_job`, and manual include/exclude behavior are all unchanged.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Enriched prompt increases token count | Acceptable — a few extra sentences per call is negligible vs. current repair/verify overhead |
| Removing `_verify_reject_with_ai` lets borderline rejects become passes | Intended — Phase 1 is a high-recall gate; Phase 2 is the precision gate |
| LLaMA 4 Scout may still misclassify with very short prompts ("SWE", "backend") | Implementer should test with minimal prompts and tune the context builder accordingly |
| Phase 2 `json_schema` format may not be supported by all Groq models | `strict: false` already used in Phase 1 for Groq compatibility — apply same flag to Phase 2 schema |
| `matched_titles` from `generated_titles` may be empty for profiles without generated titles | Fall back gracefully: use `[job.title]` when `profile.generated_titles` is empty (current behavior preserved) |
| Existing jobs incorrectly rejected at Phase 1 remain in DB | After shipping, run `rescore_account_jobs_now` to re-evaluate |

## Sources & References

- Prior plan: [docs/plans/2026-04-04-005-feat-title-first-relevance-plan.md](docs/plans/2026-04-04-005-feat-title-first-relevance-plan.md)
- Phase 1 client: [backend/app/integrations/openai/job_title_screening.py](backend/app/integrations/openai/job_title_screening.py)
- Phase 2 client: [backend/app/integrations/openai/job_relevance.py](backend/app/integrations/openai/job_relevance.py)
- Service layer: [backend/app/domains/jobs/relevance.py](backend/app/domains/jobs/relevance.py)
- Policy/hints: [backend/app/domains/jobs/relevance_policy.py](backend/app/domains/jobs/relevance_policy.py)
- Task processor: [backend/app/tasks/job_relevance.py](backend/app/tasks/job_relevance.py)
