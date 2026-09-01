# TASK-179 — Primary Console Activity Log

STATUS: COMPLETE

## Objective

Expose the existing Activity Log as a read-only primary-console register and
complete the TASK-175–179 quality gate.

## Approved scope

- List existing activity records newest first through `ActivityLogService`.
- Display only existing action, entity, identifier, details and timestamps.
- Keep the browser surface read-only.
- Run focused tests, full regression, Bugbot and the approved PR checks.

## Out of scope

New activity actions, free-text activity writes, editing, deletion, schema changes,
imports, real-data test writes, deployment and `main`.

## Allowed changed-file scope

- `tasks/TASK-179-primary-console-activity-log.md`
- `advancore/api/dependencies.py`
- `advancore/api/routes/operations.py`
- `advancore/api/schemas.py`
- `advancore/module_registry.py`
- `frontend/editing.js`
- `frontend/index.html`
- `tests/test_api_daily_operations.py`
- `tests/test_api_modules.py`
- `tests/test_primary_console_cutover.py`
- `docs/architecture/PRIMARY_CONSOLE_CUTOVER.md`

## Acceptance criteria

- [x] Activity Log is locally readable and has no mutation route.
- [x] TASK-175–179 tests and review gates are clean.
- [x] No customer, driver, company, schedule or pricing data is committed.

## Module design gate

Classification: NON_MODULE
Module identifier: None
Approved brief: None

## Completion report

- Implemented: read-only Activity Log history in the primary record manager.
- Files changed: this task file; shared API schemas, read gateway and operations
  route; module registry; primary frontend HTML/JavaScript; daily-operation,
  module and cutover tests; primary cutover record.
- Database changes: none; no Activity Log mutation route was added.
- Tests: focused API/gateway/frontend tests and isolated full regression passed.
- Assumptions: advanced filtering remains in the temporary Streamlit admin surface.
- Risks / unresolved issues: none within the read-only transfer.
- Decisions required: none for TASK-179.
- Recommended next step: publish only after Bugbot, CI and GitGuardian remain clean.
