# TASK-063 — Project Activity Recording

STATUS: REVIEW

## Objective

Record the three owner-approved Project lifecycle events in the same database
transaction as each successful create, edit, or archive mutation.

## In scope

- Inject the approved ActivityLogService into the production Project service.
- Record `project_created`, `project_updated`, and `project_archived` with entity
  type `project` and the numeric project identifier only.
- Propagate recording failures so the caller-owned transaction rolls back.
- Restore edited/archive in-memory state when activity recording fails.
- Add focused event and transaction rollback coverage.

## Out of scope

Names, descriptions, details, actors, IP/device data, credentials, deletion,
retention, compliance claims, schema changes, permissions, deployment, or
`main`.

## Allowed changed-file scope

- `tasks/TASK-063-project-activity-recording.md`
- `advancore/pages/projects.py`
- `advancore/services/project_service.py`
- `tests/test_project_service.py`

## Owner decisions

The minimal, same-transaction, fail-closed policy was approved on
24 August 2026.

## Completion report

### Implemented

- Injected ActivityLogService into the production Projects unit of work using
  the same SQLAlchemy session as ProjectRepository.
- Recorded the exact approved created, updated, and archived event codes with
  entity type `project` and numeric identifier only.
- Propagated activity failures and restored edited/archive in-memory state.
- Added exact event, mutation restoration, and database transaction rollback
  coverage.

### Files changed

- `tasks/TASK-063-project-activity-recording.md`
- `advancore/pages/projects.py`
- `advancore/services/project_service.py`
- `tests/test_project_service.py`

### Database changes

None. Existing Project and ActivityLog tables are reused.

### Tests executed and results

- Focused Project/page/activity tests: 69 passed.
- Full repository suite: 897 passed.
- `git diff --check`: passed.
- Live create/edit/archive produced exactly three minimal ActivityLog rows.
- Live Activity Log displayed `project_archived` for entity type `project`, ID
  `4`, and `Details: Not provided`.

### Assumptions

- Read-only ProjectService use in isolated tests may omit an activity service;
  the production page always injects it for mutations.

### Risks / unresolved issues

- Isolated read-only/test construction may omit activity injection; the
  production Projects page always injects it.

### Decisions required

- Review and feature-branch publication remain governed follow-up actions.

### Recommended next step

- Review and publish the integration, then connect Knowledge mutations under
  the same approved policy.
