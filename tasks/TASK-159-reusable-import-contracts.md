# TASK-159 — Reusable Import Contracts

STATUS: COMPLETE

## Objective

Make the existing preview/review/publication import workflow reusable by future
modules without allowing generic unreviewed database writes.

## In scope

- Add a code-owned import dataset contract catalog for existing datasets.
- Reuse it from preview and duplicate-review services.
- Preserve exact headers, limits, identities and owner-approved publication.

## Out of scope

- New datasets, real imports, schema changes or automatic publication.

## Database impact

None.

## Allowed changed-file scope

- `advancore/services/import_contract_registry.py`
- `advancore/services/operational_import_service.py`
- `advancore/services/operational_import_review_service.py`
- `tests/test_import_contract_registry.py`
- `tests/test_operational_import_service.py`
- `tests/test_operational_import_review_service.py`
- This task file

## Acceptance criteria

- [x] Existing imports retain identical external behavior.
- [x] Unknown datasets fail closed.
- [x] Contracts grant no publication or database authority.

## Owner decisions

None.

## Completion report

- Centralized the four existing operational CSV contracts and reused them from preview and review services.
- Existing headers, labels, identity fields, preview limits and approval-first publication remain intact.
- Existing import tests and new contract tests passed; no real import was performed.
