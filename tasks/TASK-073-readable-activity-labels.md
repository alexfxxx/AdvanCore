# TASK-073 — Readable Activity Labels

STATUS: REVIEW

## Objective

Present internal Activity Log action and entity codes as clear business-facing
labels while preserving the exact stored audit values and filter behavior.

## Business context

The Activity Log currently shows codes such as `project_created` in selectors
and details. These are useful internally but make the owner-facing interface
look technical and harder to scan.

## Facts

- Activity records store stable action and entity codes.
- Existing filters are allowlisted and exact-match.
- Streamlit can apply presentation labels without changing option values.

## In scope

- Map the six existing lifecycle action codes to readable labels.
- Show readable action labels in filters, record selection, and details.
- Show readable Project/Knowledge entity labels in details.
- Preserve exact stored values for filtering and retrieval.
- Add page regression tests and verify the live Activity Log.

## Out of scope

- Activity storage, action codes, filters, ordering, schema, retention, export,
  mutation, audit policy, business rules, or `main`.

## Allowed changed-file scope

- `tasks/TASK-073-readable-activity-labels.md`
- `advancore/pages/activity_log.py`
- `tests/test_activity_log_page.py`

## Database impact

None.

## Acceptance criteria

- [x] Known activity codes display as readable labels.
- [x] Filter and retrieval values remain the exact stored codes.
- [x] Unknown non-empty values have a safe readable fallback rather than being
      discarded.
- [x] Existing empty states and generic error boundaries remain unchanged.
- [x] Focused and full tests pass.
- [x] Completion report produced.

## Test requirements

- Test known and unknown label formatting.
- Test readable filter options, record selection, and detail output.
- Run the Activity Log page tests, full suite, and `git diff --check`.
- Inspect a live saved activity record.

## Constraints

- Do not mutate the stored audit values.
- Keep exact-match filtering.
- Do not use dynamic HTML.

## Owner decisions

None. This is presentation-only wording for existing codes.

## Completion report

### Implemented

- Added explicit presentation labels for all six existing Project and Knowledge
  lifecycle actions.
- Applied readable labels to the action filter, selected-record control, action
  detail, and entity detail.
- Preserved exact stored codes as the select/filter values and service inputs.
- Added a bounded fallback that turns future underscore-separated codes into
  readable text without discarding them.

### Files changed

- `tasks/TASK-073-readable-activity-labels.md`
- `advancore/pages/activity_log.py`
- `tests/test_activity_log_page.py`

### Database changes

None.

### Tests and results

- Focused Activity Log page tests: 8 passed.
- Full repository suite: 933 passed in 169.93 seconds.
- `git diff --check`: passed.
- Live verification showed `Knowledge archived (record #6)`, `Action:
  Knowledge archived`, and `Entity type: Knowledge` for the saved code.

### Assumptions

- None. Formatting operates only on presentation values.

### Risks / unresolved issues

- Future codes receive a generic readable fallback until a separately reviewed
  label is added; the stored code remains visible to the service layer.

### Decisions required

None.

### Recommended next step

- Publish for independent GitHub verification and integrate only into
  `projects-lifecycle-recovery` when clean.
