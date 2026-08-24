# TASK-065 — Activity Log Filters

STATUS: REVIEW

## Objective

Make the approved Activity Log easier to use by adding exact entity-type and
action filters to the existing read-only page.

## In scope

- Add `All`, Project, and Knowledge entity filters.
- Add `All` plus the six owner-approved lifecycle action filters.
- Limit the record selector to matching entries.
- Show a clear empty state when no records match.
- Keep the page read-only and add focused presentation tests.

## Out of scope

Search over names/content, new event types, free-text details, actors,
IP/device data, credentials, mutation, deletion, export, retention, schema
changes, permissions, deployment, or `main`.

## Allowed changed-file scope

- `tasks/TASK-065-activity-log-filters.md`
- `advancore/pages/activity_log.py`
- `tests/test_activity_log_page.py`

## Owner decisions

The safe Activity Log policy and continuation through TASK-066 were approved
on 24 August 2026.

## Completion report

### Implemented

- Added exact entity and action filters using only the approved values.
- Limited the record selector to matching entries.
- Added a clear no-match state and filter-specific selector state.
- Kept the Activity Log read-only.

### Files changed

- `tasks/TASK-065-activity-log-filters.md`
- `advancore/pages/activity_log.py`
- `tests/test_activity_log_page.py`

### Database changes

None.

### Tests executed and results

- Focused Activity Log tests: 21 passed.
- Full repository suite: 903 passed.
- `git diff --check`: passed.
- Live filtering to Project and Project Archived showed only the matching
  minimal record and retained `Details: Not provided`.

### Assumptions

- The six owner-approved lifecycle actions are the complete filter set for
  this bounded slice.

### Risks / unresolved issues

- Older activity codes remain visible under All actions but cannot be chosen as
  an explicit approved filter.

### Decisions required

- Review and feature-branch publication remain governed follow-up actions.

### Recommended next step

- Add a small dashboard overview of the same approved Activity Log records.
