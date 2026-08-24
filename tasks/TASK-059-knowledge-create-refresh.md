# TASK-059 — Knowledge Create Refresh

STATUS: REVIEW

## Objective

After creating a Knowledge draft, clear the creation form, show one success
notice, and select the newly created draft immediately.

## In scope

- Return the created item identifier through the existing presentation helper.
- Give creation inputs explicit bounded session keys.
- Rerun after success with cleared creation inputs and the new item selected.
- Preserve validation, generic failure handling, and list ordering.
- Add focused regression coverage.

## Out of scope

Database changes, duplicate-title policy, lifecycle changes, project linking,
search, deletion, permissions, worker routing, deployment, or `main`.

## Allowed changed-file scope

- `tasks/TASK-059-knowledge-create-refresh.md`
- `advancore/pages/knowledge_hub.py`
- `tests/test_knowledge_hub_page.py`

## Owner decisions

None. This repairs live behavior observed while verifying TASK-058.

## Completion report

### Implemented

- Captured the created identifier while the database session remains active,
  preventing detached-object errors and technical tracebacks.
- Versioned the creation widget keys after a successful save so the rerun
  receives genuinely blank fields.
- Selected the new draft, showed one bounded success notice, and retained the
  existing validation and generic-failure behavior.
- Added focused coverage for form reset, new-item selection, and the database
  session boundary.

### Files changed

- `tasks/TASK-059-knowledge-create-refresh.md`
- `advancore/pages/knowledge_hub.py`
- `tests/test_knowledge_hub_page.py`

### Database changes

None.

### Tests executed and results

- Focused Knowledge Hub page tests: 16 passed.
- Full repository suite: 877 passed.
- `git diff --check`: passed.
- Live browser create: blank form after rerun, new draft selected, success
  notice rendered, and no traceback exposed.
- All temporary TASK-059 records were archived after verification.

### Assumptions

- Newly created knowledge remains selected after the success rerun.

### Risks / unresolved issues

- No known issue within scope.

### Decisions required

- Review and feature-branch publication remain governed follow-up actions.

### Recommended next step

- Review and publish the scoped repair, then audit the equivalent Projects
  creation flow for the same class of usability defect.
