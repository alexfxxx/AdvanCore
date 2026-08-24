# TASK-049 — AI Center Owner Exception Inbox

STATUS: REVIEW

## Objective

Show the existing fail-closed orchestration exception inbox in the app so the
owner sees only genuine decisions or investigations requiring attention.

## In scope

- Render TASK-027's read-only validated inbox in AI Center.
- Show a clear all-clear state, bounded reasons, task/status and whether an
  owner decision is required.
- Never expose prompts, transcripts, source contents, credentials, environment,
  raw logs, filesystem paths, or mutation controls.
- Add deterministic page tests.

## Out of scope

Applying decisions, worker launch, repair, notifications, remote access,
authentication, merge, `main`, deployment, or database changes.

## Allowed changed-file scope

- `tasks/TASK-049-ai-center-owner-exception-inbox.md`
- `advancore/pages/ai_center.py`
- `tests/test_ai_center_page.py`
- `README.md`

## Owner decisions

None. The owner requested exception-based rather than stage-by-stage attention.

## Completion report

### Implemented

- Reused the existing validated TASK-027 inbox instead of duplicating its
  governance classification.
- Added plain all-clear, decision-required and investigation views to AI Center.
- Kept the page strictly read-only and bounded.

### Database changes

None.

### Tests executed and results

- Focused AI Center and validated inbox suites: 29 passed.
- Python compile and `git diff --check`: passed.

### Decisions required

- Independent review and implementation approval remain manual.
