# TASK-076 — Knowledge Replacement History

STATUS: REVIEW

## Objective

Allow the owner to correct approved Knowledge by creating a linked replacement
draft, while preserving every approved version and atomically retiring the old
official version only when its replacement is approved.

## Business context

TASK-074 made approved Knowledge immutable and required corrections to use a
replacement draft. TASK-075 exposed explicit owner approval. The app now needs
the governed correction path so official history is never silently rewritten.

## Facts

- Approved Knowledge title and content are read-only.
- Draft approval records fixed owner identity, UTC time, and Activity Log
  evidence in a caller-owned transaction.
- Archived approved Knowledge retains approval evidence.
- The current app is single-owner and has no authenticated identity model.
- Existing Knowledge rows have no replacement lineage and must remain valid.

## Approved lifecycle rules

- Only an `approved` item may start a replacement draft.
- The replacement draft copies the saved title, content, project link, and
  source metadata, and links back by identifier; it never mutates the source.
- At most one non-archived direct replacement may exist for one source version.
- An archived replacement draft permits a fresh replacement attempt.
- While a replacement remains a draft, the source remains the official
  approved version and cannot be archived.
- Approving a valid replacement atomically changes its source from `approved`
  to `superseded`; the replacement becomes the new `approved` version.
- Superseded Knowledge remains immutable, retains its original approval
  evidence, and cannot be archived or approved again.
- A newly approved replacement may later start its own replacement, creating a
  forward-only version chain.
- Missing, stale, ambiguous, self-referential, or unsupported transitions fail
  closed.

## In scope

- Add nullable self-replacement lineage to `KnowledgeItem`.
- Add database checks and a partial unique index for consistent open lineage.
- Add a non-destructive forward Alembic migration.
- Add repository lookup for a source's active replacement.
- Add replacement draft creation and atomic replacement approval/superseding.
- Prevent archive of an approved source while its replacement is active.
- Add minimal `knowledge_replacement_created` and `knowledge_superseded`
  Activity Log actions and readable labels.
- Add owner-facing replacement creation, lineage details, superseded state,
  selected-item refresh, and bounded success/error handling.
- Record the lifecycle decision and add focused model, migration, repository,
  service, activity, and page tests.

## Out of scope

- Deletion, rollback to an older version, branching replacement histories,
  content diffing, merge tools, rejection, notifications, search, authentication,
  roles, biometric authentication, UniFace integration, AI approval, deployment,
  or `main`.

## Allowed changed-file scope

- `tasks/TASK-076-knowledge-replacement-history.md`
- `advancore/models/knowledge.py`
- `advancore/repositories/knowledge.py`
- `advancore/services/knowledge_service.py`
- `advancore/services/activity_service.py`
- `advancore/pages/knowledge_hub.py`
- `advancore/pages/activity_log.py`
- `alembic/versions/*_knowledge_replacement_history.py`
- `docs/decisions/ADR-030-knowledge-replacement-history.md`
- `tests/test_models.py`
- `tests/test_migrations.py`
- `tests/test_postgres_knowledge_replacement_migration.py`
- `tests/test_repositories.py`
- `tests/test_knowledge_service.py`
- `tests/test_activity_service.py`
- `tests/test_activity_log_page.py`
- `tests/test_knowledge_hub_page.py`

## Database impact

- Add nullable `knowledge_items.replaces_knowledge_item_id` self-reference.
- Add a no-self-replacement check.
- Require approval metadata for `superseded` rows.
- Add a partial unique index allowing one non-archived direct replacement per
  source while permitting retry after an archived draft.
- Existing rows remain unchanged and valid.

## Acceptance criteria

- [x] Existing rows migrate without synthetic lineage or content changes.
- [x] Only approved Knowledge can create a replacement draft.
- [x] The source remains unchanged and official while the replacement is draft.
- [x] A replacement draft copies bounded saved fields and links only by numeric
      identifier.
- [x] Parallel active replacements, self-reference, and stale lineage fail
      closed.
- [x] An archived replacement draft allows a fresh attempt.
- [x] Replacement approval atomically approves the new version and supersedes
      the exact approved source.
- [x] Save or Activity Log failure restores both in-memory lifecycle states and
      rolls back the caller-owned transaction.
- [x] Superseded Knowledge remains read-only and retains approval evidence.
- [x] The owner UI clearly shows source/replacement lineage and never rewrites
      approved content.
- [x] Activity events contain only action, entity type, and numeric entity ID.
- [x] Focused and full tests pass.
- [x] Completion report produced.

## Test requirements

- Cover model metadata, constraints, partial unique index, and migration safety.
- Run the real forward migration against GitHub's disposable PostgreSQL service
  while skipping every local saved database.
- Cover replacement creation, copying, active uniqueness, archived retry,
  atomic approval/superseding, all failure restoration, and real transaction
  rollback.
- Cover Activity Log allowlist, filters, labels, and minimal event sequences.
- Cover owner confirmation, selected replacement refresh, lineage presentation,
  superseded read-only state, active-replacement archive prevention, and
  generic unexpected failures.
- Run focused tests, full repository tests, `git diff --check`, compilation,
  Alembic lineage, and GitHub CI/security checks.

## Constraints

- Preserve page → service → repository → session dependency direction.
- Preserve approved title/content and approval evidence byte-for-byte.
- Do not accept caller-supplied approver identity.
- Do not place Knowledge title/content, credentials, biometrics, or free text in
  Activity Log details or success notices.
- Do not add authentication, UniFace, or an agent-callable approval path.

## Owner decisions

The owner authorised continuation with TASK-076 on 25 August 2026. The approved
TASK-074 rule that corrections use replacement drafts remains authoritative.

## Completion report

### Implemented

- Added forward-only replacement lineage with database-enforced self-reference
  and active-successor safeguards.
- Added owner-confirmed correction-draft creation that copies saved business
  fields without changing the approved source.
- Added atomic replacement approval: the new version becomes approved while its
  exact source becomes superseded in the same caller-owned transaction.
- Added archive/retry rules, superseded read-only presentation, lineage details,
  selected-draft refresh, and minimal Activity Log actions.

### Files changed

- Knowledge model, repository, service, and Knowledge Hub page.
- Activity Log policy and presentation.
- One forward migration, ADR-030, and the governed task record.
- Focused model, migration, PostgreSQL, repository, service, activity, and page
  tests.

### Database changes

- Adds nullable `replaces_knowledge_item_id` self-reference.
- Adds no-self-reference and superseded-metadata checks.
- Adds a partial unique index for one non-archived direct replacement.
- Existing rows are not rewritten.

### Tests and results

- Focused replacement, Knowledge, migration, repository, and audit tests:
  119 passed, 1 intentionally skipped locally.
- Full repository suite: 975 passed, 2 intentionally skipped in 169.74 seconds.
- Compilation, `git diff --check`, and Alembic head/history passed.
- GitHub PR #17 CI passed, including the real migration against its disposable
  PostgreSQL service; GitGuardian also passed.

### Assumptions

- One forward-only direct successor per approved version is the safest bounded
  interpretation of immutable replacement history.

### Risks / unresolved issues

- History is intentionally linear; branching, rollback, and content diffing are
  not included.

### Decisions required

None for this approved scope.

### Recommended next step

Merge green PR #17 into `projects-lifecycle-recovery` (never `main`), then
evaluate the next owner-prioritised capability separately.
