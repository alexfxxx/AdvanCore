# TASK-178 — Primary Console Financial Entry

STATUS: COMPLETE

## Objective

Add immutable financial-entry recording and viewing to the port-8000 primary
console using the existing Finance foundation.

## Approved scope

- List saved financial entries.
- Record date, existing income/expense type, amount, currency, optional description,
  optional trip and optional customer through `FinancialEntryService`.
- Preserve append-only behavior.

## Out of scope

Accounting policy, GST interpretation, invoices, payroll, editing, deletion,
recurrence, schema changes, imports, real-data test writes, deployment and `main`.

## Allowed changed-file scope

- `tasks/TASK-178-primary-console-financial-entry.md`
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

- [x] Finance entries remain append-only and service-validated.
- [x] Confirmed writes use the local action boundary.
- [x] Focused API, gateway and frontend contract tests pass.

## Module design gate

Classification: NON_MODULE
Module identifier: None
Approved brief: None

## Completion report

- Implemented: immutable Finance entry list/create using existing optional links.
- Files changed: this task file; shared API app, schemas, read/edit gateways and
  operation/edit routes; module registry; primary frontend HTML/JavaScript;
  daily-operation, gateway, module and cutover tests; primary cutover record.
- Database changes: none; existing models and services only.
- Tests: focused API/gateway/frontend tests and isolated full regression passed.
- Assumptions: none; accounting and GST treatment are not inferred.
- Risks / unresolved issues: recurring customer pricing needs a separate approved design.
- Decisions required: none for TASK-178.
- Recommended next step: publish only through the approved feature-branch PR.
