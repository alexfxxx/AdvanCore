# TASK-072 — Lifecycle Date Visibility

STATUS: REVIEW

## Objective

Show the existing creation and last-updated timestamps in Project and Knowledge
detail views using the readable UTC format introduced by TASK-071.

## Business context

Owners need to know when a saved project or knowledge draft was created and
last changed. Those audit values already exist in PostgreSQL but are not fully
visible: Projects show neither value and Knowledge shows only creation time.

## Facts

- Project and Knowledge models already include `created_at` and `updated_at`.
- TASK-071 provides a tested human-readable UTC formatter.
- The values are read-only audit metadata in this task.

## In scope

- Show `Created` and `Last updated` in Project details.
- Show `Last updated` alongside the existing `Created` value in Knowledge
  details.
- Use the shared formatter and retain `Not available` fallbacks.
- Add isolated page tests and verify live saved records.

## Out of scope

- Timestamp storage, schema, migrations, edit/archive behavior, ordering,
  timezone settings, activity policy, business rules, or `main`.

## Allowed changed-file scope

- `tasks/TASK-072-lifecycle-date-visibility.md`
- `advancore/pages/projects.py`
- `advancore/pages/knowledge_hub.py`
- `tests/test_projects_page.py`
- `tests/test_knowledge_hub_page.py`

## Database impact

None.

## Acceptance criteria

- [x] Project details show readable creation and last-updated values.
- [x] Knowledge details show readable creation and last-updated values.
- [x] Missing values use the existing safe fallback.
- [x] Existing create, edit, archive, and read-only behavior is unchanged.
- [x] Focused and full tests pass.
- [x] Completion report produced.

## Test requirements

- Cover populated and missing lifecycle values in both page test suites.
- Run focused Project/Knowledge tests, the full suite, and `git diff --check`.
- Inspect real saved Project and Knowledge details in the local test app.

## Constraints

- Reuse the TASK-071 formatter.
- Do not mutate or infer timestamps.
- Keep the change presentation-only.

## Owner decisions

None. This exposes existing read-only audit metadata.

## Completion report

### Implemented

- Added read-only `Created` and `Last updated` values to Project details.
- Added read-only `Last updated` alongside the existing Knowledge creation
  value.
- Reused the shared UTC formatter and kept safe missing-value behavior.
- Added Project and Knowledge page regression coverage for real and missing
  lifecycle values.

### Files changed

- `tasks/TASK-072-lifecycle-date-visibility.md`
- `advancore/pages/projects.py`
- `advancore/pages/knowledge_hub.py`
- `tests/test_projects_page.py`
- `tests/test_knowledge_hub_page.py`

### Database changes

None.

### Tests and results

- Focused Project and Knowledge page tests: 44 passed.
- Full repository suite: 932 passed in 167.10 seconds.
- `git diff --check`: passed.
- Live Project detail showed both lifecycle values for a saved record.
- Live Knowledge detail showed both lifecycle values for a saved record.

### Assumptions

- None beyond the established UTC model convention documented in TASK-071.

### Risks / unresolved issues

- Timestamps are read-only and UTC. Configurable local display time remains a
  future product decision.

### Decisions required

None.

### Recommended next step

- Publish for independent GitHub verification and integrate only into
  `projects-lifecycle-recovery` when clean.
