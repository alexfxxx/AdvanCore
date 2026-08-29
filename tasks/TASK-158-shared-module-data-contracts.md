# TASK-158 — Shared Module Data Contracts

STATUS: COMPLETE

## Objective

Document the minimum cross-module rules for identifiers, companies, money,
dates, sources, documents and lifecycle state without adding schema.

## In scope

- Define reusable data conventions and explicit non-assumptions.
- Define when a module requires fresh owner and migration approval.
- Add a documentation contract test.

## Out of scope

- Models, migrations, tables, columns, legal conclusions or retention periods.

## Database impact

None.

## Allowed changed-file scope

- `docs/architecture/MODULE_DATA_CONTRACTS.md`
- `tests/test_module_contract_docs.py`
- This task file

## Acceptance criteria

- [x] Shared conventions do not invent business fields.
- [x] Company ownership and source provenance are addressed.
- [x] Schema work remains separately approval-gated.

## Owner decisions

None.

## Completion report

- Documented shared identity, company, money, date, source and lifecycle conventions.
- The contract explicitly avoids assuming Advan owns every record or that every module needs every field.
- Database migrations and retention decisions remain separately owner-approved.
