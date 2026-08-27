# TASK-111 — Financial Record Foundation

STATUS: APPROVED

## Objective
Store immutable, explicitly denominated income and expense facts without inventing profitability.

## In scope
Calendar date, income/expense type, positive exact amount, explicit three-letter currency, optional description and real trip/customer links, additive migration, repository/service, and tests.

## Explicitly out of scope
Profit forecasts, taxes, accounting advice, exchange rates, inferred totals, editing/deletion, live migration, deployment, production, or `main`.

## Allowed changed-file scope
- `advancore/models/financial_entry.py`
- `advancore/models/__init__.py`
- `advancore/repositories/financial_entry.py`
- `advancore/repositories/__init__.py`
- `advancore/services/financial_entry_service.py`
- `alembic/versions/d1e111fin_financial_entries.py`
- `tests/test_financial_entry_service.py`
- `tasks/TASK-111-financial-records.md`

## Database impact
One additive `financial_entries` table, not applied live during implementation.

## Acceptance criteria
Every amount has an explicit currency; optional links must exist; unsupported precision is rejected; no fabricated totals; entries immutable; tests and Bugbot clean.

## Test requirements
Focused date/type/amount/currency/link/model/migration checks and full isolated regression.

## Constraints
Preserve governance; GitHub source of truth; merge only to `projects-lifecycle-recovery`.

## Owner decisions
None; reporting, tax, exchange-rate, and profitability rules remain deferred.

## Completion report

- Implemented immutable, explicitly denominated financial entry model,
  repository, service, migration, and isolated tests without applying it live.
- ASCII currency rules are enforced in both service and database constraints;
  unsupported amount precision is rejected rather than rounded.
- Focused checks: 24 passed. Full isolated suite: 1,176 passed and 2
  PostgreSQL-only skips. Whitespace check: passed.
- Bugbot's two currency findings were repaired; final rerun: clean.
- No decisions required; next step is non-main PR publication.
