# TASK-116 — Governed Master-Record Import Publication

STATUS: COMPLETE

## Objective

Allow an operator to publish one fully clean reviewed CSV batch into the
selected operational master register through existing validated services and
an explicit confirmation gate.

## Business context

Preview and duplicate review are useful only if approved records can later be
created safely. Publication must remain deliberate, atomic, and governed by
the same rules as manual record creation.

## In scope

- A fail-closed publication service for fully ready review batches.
- Explicit operator confirmation before any write.
- Publication through existing vehicle, driver, customer, and route services.
- One database transaction per batch with rollback on any error.
- Clear success/failure messaging without exposing uploaded values in logs.
- Focused service and presentation tests using synthetic non-real records.

## Out of scope

- Importing real data during development, partial-batch publication, updates or
  overwrites, migrations, fuzzy matching, credentials, billing, deployment, or
  `main`.

## Allowed changed-file scope

- `tasks/TASK-116-governed-import-publication.md`
- `advancore/services/operational_import_publication_service.py`
- `advancore/pages/operations.py`
- `tests/test_operational_import_publication_service.py`
- `tests/test_operations_page.py`

## Database impact

No schema change. Future operator-confirmed use can add master records through
existing service and transaction boundaries. This implementation run imports
no records.

## Acceptance criteria

- [ ] Empty, unconfirmed, or partly blocked batches cannot publish.
- [ ] Every ready row is passed to the existing dataset service in one batch.
- [ ] Any domain/duplicate failure rolls back the batch and shows a bounded
      message.
- [ ] No update, overwrite, or partial skip path exists.
- [ ] Development and tests use no real personal or business data.
- [ ] Focused and full tests pass; Bugbot, CI, and GitGuardian are clean.

## Owner decisions

None. The conservative all-rows-clean rule avoids partial or ambiguous imports.

## Completion report

### Implemented

- Added a fail-closed publication service requiring explicit confirmation and
  a fully ready non-empty batch.
- Routed future publication through existing master-record services within one
  dataset transaction.
- Added an operator confirmation gate, bounded errors, and success refresh.

### Files changed

- `tasks/TASK-116-governed-import-publication.md`
- `advancore/services/operational_import_publication_service.py`
- `advancore/pages/operations.py`
- `tests/test_operational_import_publication_service.py`
- `tests/test_operations_page.py`

### Database changes

None during implementation. Tests use fake services and synthetic records.

### Tests and results

- Focused: `37 passed in 1.84s`.
- Full repository: `1212 passed, 2 skipped in 176.99s`.
- `git diff --check`: passed.

### Assumptions

One uploaded file represents one atomic batch.

### Risks / unresolved issues

The operator remains responsible for confirming that future real data is
accurate and lawfully handled.

### Decisions required

None.

### Recommended next step

Implement TASK-117 daily dispatch and assignment board after integration.
