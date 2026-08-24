# TASK-060 — Project Create Refresh

STATUS: REVIEW

## Objective

After creating a project, clear the creation form, show one success notice, and
select the newly created active project immediately.

## In scope

- Capture the created identifier inside the active database scope.
- Version and clear the project creation inputs after success.
- Select the new project and rerun with one bounded success notice.
- Preserve validation, exact-name uniqueness, list order, and generic failures.
- Add focused regression coverage.

## Out of scope

Database changes, uniqueness-policy changes, lifecycle changes, search,
deletion, permissions, worker routing, deployment, or `main`.

## Allowed changed-file scope

- `tasks/TASK-060-project-create-refresh.md`
- `advancore/pages/projects.py`
- `tests/test_projects_page.py`

## Owner decisions

None. This applies the verified TASK-059 usability pattern to Projects.

## Completion report

### Implemented

- Captured the created project identifier while its database session remains
  active.
- Versioned the creation input keys after success so the rerun presents blank
  fields.
- Selected the newly created project and rendered one trusted success notice.
- Added focused coverage for creation refresh and the database session
  boundary, while improving selector-state realism in the page fake.

### Files changed

- `tasks/TASK-060-project-create-refresh.md`
- `advancore/pages/projects.py`
- `tests/test_projects_page.py`

### Database changes

None.

### Tests executed and results

- Focused Projects page tests: 25 passed.
- Full repository suite: 878 passed.
- `git diff --check`: passed.
- Live browser create: blank form, new active project selected, success notice,
  and no technical error.
- Temporary TASK-060 project archived after verification.

### Assumptions

- The newly created project remains selected after the success rerun.

### Risks / unresolved issues

- The live archive exposed a stale selector label without the archived suffix;
  the saved status and details were correct. This is deferred to TASK-061.

### Decisions required

- Review and feature-branch publication remain governed follow-up actions.

### Recommended next step

- Review and publish the scoped repair, then fix the separately observed
  Project selector-label refresh defect.
