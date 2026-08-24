# TASK-062 — Activity Recording Foundation

STATUS: REVIEW

## Objective

Add a fail-closed service/repository foundation for the six owner-approved
project and knowledge lifecycle activity codes without recording sensitive or
free-text data.

## In scope

- Add ActivityLog repository persistence inside a caller-owned transaction.
- Add service validation for exactly six approved action/entity combinations.
- Accept only positive integer entity identifiers and store them as strings.
- Always store `details=None` and expose no parameter for names/content/details.
- Add focused repository and service coverage.

## Out of scope

Connecting project/knowledge mutations, actors, names, descriptions, content,
IP/device data, credentials, details, retention, compliance claims, schema
changes, permissions, deployment, or `main`.

## Allowed changed-file scope

- `tasks/TASK-062-activity-recording-foundation.md`
- `advancore/repositories/activity.py`
- `advancore/services/activity_service.py`
- `tests/test_activity_service.py`
- `tests/test_repositories.py`

## Owner decisions

The owner approved on 24 August 2026:

- actions: project/knowledge created, updated, archived;
- stored values: action code, entity type, numeric identifier only;
- no free-text or sensitive fields;
- same-transaction, fail-closed recording when connected by later tasks.

## Completion report

### Implemented

- Added ActivityLog repository persistence within a caller-owned transaction.
- Added exact validation for the six approved action/entity combinations and
  positive integer identifiers.
- Constructed records with action, entity type, string identifier, and
  `details=None`; no API accepts free-text details.
- Added repository persistence and service allowlist/rejection coverage.

### Files changed

- `tasks/TASK-062-activity-recording-foundation.md`
- `advancore/repositories/activity.py`
- `advancore/services/activity_service.py`
- `tests/test_activity_service.py`
- `tests/test_repositories.py`

### Database changes

None. The existing `activity_logs` table is reused.

### Tests executed and results

- Focused activity service/repository tests: 24 passed.
- Full repository suite: 893 passed.
- `git diff --check`: passed.

### Assumptions

- Entity types are exactly `project` and `knowledge`.

### Risks / unresolved issues

- No lifecycle mutation is connected in this foundation task.
- Recording failure behavior will be verified with each same-transaction
  integration in TASK-063 and TASK-064.

### Decisions required

- Review and feature-branch publication remain governed follow-up actions.

### Recommended next step

- Review and publish the foundation, then connect Project lifecycle mutations
  using the same caller-owned database session.
