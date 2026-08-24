# TASK-064 — Knowledge Activity Recording

STATUS: REVIEW

## Objective

Record the three owner-approved Knowledge lifecycle events in the same database
transaction as each successful create, edit, or archive mutation.

## In scope

- Inject the approved ActivityLogService into the production Knowledge service.
- Record `knowledge_created`, `knowledge_updated`, and `knowledge_archived` with
  entity type `knowledge` and the numeric item identifier only.
- Propagate recording failures so the caller-owned transaction rolls back.
- Restore edited/archive in-memory state when activity recording fails.
- Add focused event and transaction rollback coverage.

## Out of scope

Titles, content, details, actors, IP/device data, credentials, deletion,
retention, compliance claims, schema changes, permissions, deployment, or
`main`.

## Allowed changed-file scope

- `tasks/TASK-064-knowledge-activity-recording.md`
- `advancore/pages/knowledge_hub.py`
- `advancore/services/knowledge_service.py`
- `tests/test_knowledge_service.py`

## Owner decisions

The minimal, same-transaction, fail-closed policy was approved on
24 August 2026.

## Completion report

### Implemented

- Injected ActivityLogService into the production Knowledge unit of work using
  the same SQLAlchemy session as KnowledgeItemRepository.
- Recorded the exact approved created, updated, and archived event codes with
  entity type `knowledge` and numeric identifier only.
- Propagated activity failures and restored edited/archive in-memory state.
- Added exact event, mutation restoration, and database rollback coverage.

### Files changed

- `tasks/TASK-064-knowledge-activity-recording.md`
- `advancore/pages/knowledge_hub.py`
- `advancore/services/knowledge_service.py`
- `tests/test_knowledge_service.py`

### Database changes

None. Existing KnowledgeItem and ActivityLog tables are reused.

### Tests executed and results

- Focused Knowledge/page/activity tests: 51 passed.
- Full repository suite: 901 passed.
- `git diff --check`: passed.
- Live create/edit/archive produced exactly three minimal ActivityLog rows.
- Live Activity Log displayed `knowledge_archived` for entity type `knowledge`,
  ID `7`, and `Details: Not provided`.

### Assumptions

- Read-only KnowledgeService use in isolated tests may omit an activity service;
  the production page always injects it for mutations.

### Risks / unresolved issues

- Isolated read-only/test construction may omit activity injection; the
  production Knowledge page always injects it.

### Decisions required

- Review and feature-branch publication remain governed follow-up actions.

### Recommended next step

- Add bounded Activity Log filtering so the approved records are easier to use.
