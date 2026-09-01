# TASK-176 — Primary Console Trip Assignments

STATUS: COMPLETE

## Objective

Expose the existing trip-assignment workflow in the port-8000 primary console.

## Approved scope

- List existing assignment records.
- Assign one existing planned trip to one active vehicle and one active driver.
- Release an assigned record through `TripAssignmentService`.
- Preserve the existing one-assignment-record-per-trip rule.

## Out of scope

Replacement assignments, deletion, availability-policy changes, automated dispatch,
schema changes, imports, real-data test writes, deployment and `main`.

## Allowed changed-file scope

- `tasks/TASK-176-primary-console-trip-assignments.md`
- `advancore/api/app.py`
- `advancore/api/dependencies.py`
- `advancore/api/editing_gateway.py`
- `advancore/api/routes/editing.py`
- `advancore/api/routes/operations.py`
- `advancore/api/schemas.py`
- `advancore/module_registry.py`
- `frontend/app.js`
- `frontend/editing.js`
- `frontend/index.html`
- `tests/test_api_daily_operations.py`
- `tests/test_api_modules.py`
- `tests/test_editing_gateway.py`
- `tests/test_primary_console_cutover.py`
- `docs/architecture/PRIMARY_CONSOLE_CUTOVER.md`

## Acceptance criteria

- [x] Reads and confirmed assign/release actions use existing services exclusively.
- [x] Invalid or stale selections fail closed.
- [x] Focused API, gateway and frontend contract tests pass.

## Module design gate

Classification: NON_MODULE
Module identifier: None
Approved brief: None

## Completion report

- Implemented: Assignment list/create/release with existing planned-trip and active-resource rules.
- Files changed: this task file; shared API app, schemas, read/edit gateways and
  operation/edit routes; module registry; primary frontend HTML/JavaScript;
  daily-operation, gateway, module and cutover tests; primary cutover record.
- Database changes: none; existing models and services only.
- Tests: focused API/gateway/frontend tests and isolated full regression passed.
- Assumptions: none; released assignment records remain historical and cannot be replaced.
- Risks / unresolved issues: replacement assignment policy remains outside scope.
- Decisions required: none for TASK-176.
- Recommended next step: publish only through the approved feature-branch PR.
