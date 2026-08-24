# TASK-061 — Project Selector Refresh

STATUS: REVIEW

## Objective

Ensure the Project selector immediately displays the saved name/status label
after an edit or archive while keeping the same project selected.

## In scope

- Version the selector widget from current saved project labels.
- Preserve the selected project separately across label-changing reruns.
- Remove legacy and superseded selector-widget state before rendering.
- Add regression coverage for the observed active-to-archived transition.

## Out of scope

Lifecycle changes, sorting changes, search, database changes, deletion,
permissions, worker routing, deployment, or `main`.

## Allowed changed-file scope

- `tasks/TASK-061-project-selector-refresh.md`
- `advancore/pages/projects.py`
- `tests/test_projects_page.py`

## Owner decisions

None. This is the Projects equivalent of the verified TASK-058 repair.

## Completion report

### Implemented

- Versioned the Project selectbox key from a digest of current project IDs,
  names, and statuses without placing raw values in the key.
- Preserved the selected project separately across label-changing reruns.
- Removed legacy and superseded selector widget state before rendering.
- Added exact active-to-archived regression coverage.

### Files changed

- `tasks/TASK-061-project-selector-refresh.md`
- `advancore/pages/projects.py`
- `tests/test_projects_page.py`

### Database changes

None.

### Tests executed and results

- Focused Projects page tests: 26 passed.
- Full repository suite: 879 passed.
- `git diff --check`: passed.
- Live browser archive: the same selected project immediately displayed its
  archived suffix and correct read-only details.

### Assumptions

- Existing creation-order list behavior remains unchanged.

### Risks / unresolved issues

- No known issue within scope. Creation-order behavior is unchanged.

### Decisions required

- Review and feature-branch publication remain governed follow-up actions.

### Recommended next step

- Review and publish the scoped repair, then continue the bounded usability
  backlog.
