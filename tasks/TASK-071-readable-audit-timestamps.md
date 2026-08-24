# TASK-071 — Readable Audit Timestamps

STATUS: REVIEW

## Objective

Replace machine-formatted creation timestamps in the Knowledge and Activity
interfaces with consistent, human-readable UTC dates while leaving stored
audit values unchanged.

## Business context

The owner asked for a layman-friendly application. Knowledge details and
Activity details currently expose raw ISO values such as
`2026-08-23T10:30:00`, which are accurate but unnecessarily technical.

## Facts

- Knowledge and Activity records use the shared timestamp model fields.
- The timestamp defaults are generated in UTC.
- This task changes presentation only; raw storage and audit ordering remain
  unchanged.

## In scope

- Add one shared, deterministic UTC timestamp formatter for user-facing pages.
- Show `DD Mon YYYY, HH:MM UTC` in Knowledge and Activity details.
- Keep the existing `Not available` fallback for absent timestamps.
- Add unit and page regression tests, including aware-timezone conversion.

## Out of scope

- Database or schema changes, user-configurable timezone settings, local-time
  inference, timestamp mutation, activity ordering, business rules, or `main`.

## Allowed changed-file scope

- `tasks/TASK-071-readable-audit-timestamps.md`
- `advancore/ui/formatting.py`
- `advancore/pages/knowledge_hub.py`
- `advancore/pages/activity_log.py`
- `tests/test_ui_formatting.py`
- `tests/test_knowledge_hub_page.py`
- `tests/test_activity_log_page.py`

## Database impact

None.

## Acceptance criteria

- [x] Knowledge and Activity creation times use one readable UTC format.
- [x] Naive stored values are explicitly treated as UTC, consistent with the
      current model default.
- [x] Aware values are converted to UTC before display.
- [x] Missing timestamps retain the existing fallback.
- [x] Focused and full tests pass.
- [x] Completion report produced.

## Test requirements

- Unit-test naive UTC, aware timezone conversion, and absent values.
- Update both page tests for the readable text.
- Run focused formatter/page tests, the full suite, and `git diff --check`.

## Constraints

- Do not change stored timestamps or their ordering.
- Do not assume the owner's local timezone is the timezone of all future users.
- Keep formatting dependency-free.

## Owner decisions

None. UTC is the existing storage convention; configurable display timezones
remain a separate future decision.

## Completion report

### Implemented

- Added a shared dependency-free formatter that renders timestamps as
  `DD Mon YYYY, HH:MM UTC`.
- Treated naive values as UTC in line with the existing model default and
  converted timezone-aware values to UTC before display.
- Applied the formatter to Knowledge details and Activity details without
  changing stored values, audit ordering, or missing-value behavior.
- Added formatter and page regression coverage.

### Files changed

- `tasks/TASK-071-readable-audit-timestamps.md`
- `advancore/ui/formatting.py`
- `advancore/pages/knowledge_hub.py`
- `advancore/pages/activity_log.py`
- `tests/test_ui_formatting.py`
- `tests/test_knowledge_hub_page.py`
- `tests/test_activity_log_page.py`

### Database changes

None.

### Tests and results

- Focused formatter, Knowledge, and Activity tests: 27 passed.
- Full repository suite: 931 passed in 169.90 seconds.
- `git diff --check`: passed.
- Live Knowledge verification displayed `24 Aug 2026, 12:08 UTC`.
- Live Activity verification displayed `24 Aug 2026, 13:30 UTC`.

### Assumptions

- Naive timestamp values follow the current model convention and represent UTC.

### Risks / unresolved issues

- The application still has no owner-configurable display timezone. UTC is
  explicit and unambiguous until that product decision is made.

### Decisions required

None.

### Recommended next step

- Publish for independent GitHub verification and integrate only into
  `projects-lifecycle-recovery` when clean.
