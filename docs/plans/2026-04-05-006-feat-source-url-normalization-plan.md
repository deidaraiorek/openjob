---
title: feat: Normalize ATS source URLs before sync
type: feat
status: active
date: 2026-04-05
origin: docs/plans/2026-04-02-001-feat-job-application-autopilot-plan.md
---

# feat: Normalize ATS source URLs before sync

## Overview

Make source sync resilient to the different URL shapes real ATS boards expose, especially Greenhouse embed URLs like `https://job-boards.greenhouse.io/embed/job_board?for=Stripe`. The system should derive the canonical source identifier from either explicit settings or the entered URL instead of assuming one path shape.

## Problem Frame

Sync currently assumes a Greenhouse board token is the first URL path segment. That works for simple board URLs like `/stripe` but fails for embed URLs where the real token lives in the query string. The result is a `500` or a bad fetch even though the user entered a valid ATS board URL.

## Key Decisions

- Keep source creation simple: users can continue pasting normal human-facing board URLs.
- Normalize URLs server-side during sync instead of forcing users to pre-convert them.
- Prefer explicit settings when present, then derive from URL.
- Support the common URL families for each ATS rather than a single path pattern.
- Return validation errors when a URL truly cannot be normalized, not generic sync failures.

## Scope

- This plan covers Greenhouse and Lever source URL derivation.
- This plan does not redesign the source form UX beyond surfacing better errors.
- This plan does not add browser scraping for unsupported boards.

## Implementation Units

- [ ] **Unit 1: Add ATS URL normalization helpers**

**Files**
- Update: `backend/app/tasks/discovery.py` or extract to `backend/app/domains/sources/url_normalization.py`
- Create: `backend/tests/domains/test_source_url_normalization.py`

**Design Notes**
- Greenhouse should support:
  - board URLs like `/stripe`
  - job-board URLs like `/stripe/jobs/...`
  - embed URLs with `?for=stripe`
- Lever should support:
  - company board URLs like `/company`
  - posting URLs where the first path segment still identifies the company slug
- Normalize tokens/slugs consistently before downstream fetches.

**Test Scenarios**
- Greenhouse embed URL derives `stripe`
- Greenhouse board URL derives `stripe`
- Greenhouse job posting URL still derives `stripe`
- Lever board URL derives the company slug
- Invalid ATS URL raises a clean validation error

- [ ] **Unit 2: Wire normalized identifiers into sync and keep errors user-facing**

**Files**
- Update: `backend/app/tasks/discovery.py`
- Update: `backend/app/domains/sources/routes.py`
- Update: `frontend/src/routes/sources.tsx`
- Update: `backend/tests/domains/test_source_routes.py`

**Design Notes**
- Sync should call normalization helpers before fetching.
- Route should convert normalization failures into `400` responses.
- Frontend should continue showing the exact backend error message.

**Test Scenarios**
- Syncing a Greenhouse embed URL succeeds
- Bad URL returns a specific validation message instead of `Unable to sync right now`

## Success Criteria

- Valid Greenhouse embed URLs sync successfully.
- Common ATS URL formats no longer depend on one brittle path assumption.
- Users see a specific validation error when the URL truly cannot be normalized.
