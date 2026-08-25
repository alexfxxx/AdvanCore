# TASK-074 — Knowledge Approval Foundation

STATUS: REVIEW

## Objective

Establish the database, service, and audit foundation for an owner-only,
fail-closed transition from editable Knowledge draft to official read-only
Knowledge, without yet adding the owner-facing approval button.

## Business context

Knowledge Hub currently captures drafts but cannot distinguish owner-approved
official information. The owner approved a lifecycle in which only the owner
can approve, approved content is immutable, approval is auditable, AI cannot
self-approve, and corrections use a later replacement-draft workflow.

## Facts

- Knowledge items currently use `draft` and `archived` lifecycle states.
- Existing non-draft items are already rejected by the edit service.
- Knowledge mutations and Activity Log writes share one transaction in the
  production page.
- The current app is single-owner and has no authentication identity model.
- TASK-075 will add the explicit owner review/confirmation interface.
- TASK-076 will add approved-knowledge replacement history.

## Approved lifecycle rules

- `draft → approved` is a one-way owner approval transition.
- Approved content and title are read-only.
- Approved knowledge may be archived, retaining its approval metadata.
- Approval never transitions back to draft.
- Corrections require a new replacement draft in TASK-076.
- The service records the fixed single-owner identity `owner`; it accepts no
  caller-supplied approver identity.
- AI and implementation workers receive no direct approval interface.

## In scope

- Add nullable `approved_at` and `approved_by` fields to KnowledgeItem.
- Add database constraints that keep approval fields paired, require them for
  `approved`, forbid them for `draft`, and allow archived approved history.
- Add a forward Alembic migration without rewriting the baseline.
- Add `approve_draft(item_id)` with fixed owner identity, UTC time, one-way
  lifecycle checks, persistence rollback restoration, and same-transaction
  `knowledge_approved` activity recording.
- Preserve approval metadata when approved knowledge is archived.
- Add `knowledge_approved` to the bounded Activity Log policy and readable
  filter labels.
- Record the approved lifecycle in an architecture/product decision.
- Add focused model, migration, service, activity, and presentation tests.

## Out of scope

- Approval button/form, login, multi-user identity, roles, permissions, owner
  delegation, rejection, unapproval, direct approved-content edits, replacement
  drafts, version lineage, notifications, AI approval, deployment, or `main`.

## Allowed changed-file scope

- `tasks/TASK-074-knowledge-approval-foundation.md`
- `advancore/models/knowledge.py`
- `advancore/services/knowledge_service.py`
- `advancore/services/activity_service.py`
- `advancore/pages/activity_log.py`
- `alembic/versions/*_knowledge_approval_foundation.py`
- `docs/decisions/ADR-029-knowledge-approval-lifecycle.md`
- `tests/test_models.py`
- `tests/test_migrations.py`
- `tests/test_postgres_knowledge_approval_migration.py`
- `tests/test_knowledge_service.py`
- `tests/test_activity_service.py`
- `tests/test_activity_log_page.py`

## Database impact

- Add nullable `knowledge_items.approved_at` timezone-aware datetime.
- Add nullable `knowledge_items.approved_by` string up to 100 characters.
- Add non-destructive approval-consistency check constraints.
- Existing rows remain valid and unchanged because both new fields default to
  null.

## Acceptance criteria

- [x] Existing rows migrate without synthetic approval data.
- [x] A draft can be approved exactly once and becomes read-only.
- [x] Approval always stores an aware UTC time and fixed `owner` identity.
- [x] No API accepts an arbitrary approver identity.
- [x] Approved knowledge can be archived without losing approval metadata.
- [x] Unsupported, archived, missing, and already-approved transitions fail
      closed without persistence.
- [x] Approval and audit-record failures restore in-memory lifecycle fields and
      roll back the caller-owned transaction.
- [x] Exactly one minimal `knowledge_approved` event is recorded on success.
- [x] Database constraints reject inconsistent approval metadata.
- [x] Focused and full tests pass.
- [x] Completion report produced.

## Test requirements

- Cover model columns and approval constraints.
- Validate forward migration additions and non-destructive upgrade operations.
- Cover success, fixed approver, aware UTC time, all invalid transitions,
  immutability, archive preservation, save failure, activity failure, and real
  transaction rollback.
- Cover Activity Log allowlist and readable label/filter behavior.
- Run focused tests, full repository tests, `git diff --check`, and the GitHub
  PostgreSQL migration verification.

## Constraints

- Preserve page → service → repository → session dependency direction.
- Keep approval metadata out of Activity Log details; record only action,
  entity type, and numeric entity identifier.
- Do not expose a production approval path before TASK-075 confirmation UI.
- `agent_runner`, Kimi/Codex routing, credentials, and publication governance
  remain unchanged.

## Owner decisions

The owner approved the recommended Knowledge Approval rules and authorized
TASK-074 on 25 August 2026.

## Completion report

### Implemented

- Added owner-only, one-way draft approval with a fixed `owner` identity and
  aware UTC approval time.
- Made approved Knowledge read-only while allowing archive without erasing
  approval evidence.
- Added database-enforced approval consistency and minimal Activity Log
  recording.
- Added no approval button or agent-callable approval path; TASK-075 remains
  the explicit owner confirmation interface.

### Files changed

- Knowledge model, service, Activity Log policy and presentation.
- One forward Alembic migration and ADR-029.
- Focused model, migration, PostgreSQL migration, service, activity, and page
  tests.

### Database changes

- Adds nullable `approved_at` and `approved_by` columns.
- Adds four non-destructive consistency checks; existing rows are not rewritten.

### Tests and results

- Focused: 66 passed, 1 intentionally skipped locally.
- Full repository: 950 passed, 1 intentionally skipped in 166.40 seconds.
- `git diff --check`, Alembic head/history, and Python compilation passed.
- GitHub PR #15 CI passed, including the real migration against its disposable
  PostgreSQL service database; GitGuardian also passed.

### Assumptions

- The fixed `owner` approver is temporary until a separately approved identity
  and authentication model exists.

### Risks / unresolved issues

- Owner approval is not yet available in the app; this is intentional until
  TASK-075 adds the explicit review and confirmation interface.

### Decisions required

None for this approved scope.

### Recommended next step

Merge green PR #15 into `projects-lifecycle-recovery` (never `main`), then
proceed to TASK-075 owner approval UI.
